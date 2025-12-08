"""
Memory Leak Patterns and Detection Rules with Auto-Fix Support
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Callable
import re


class LeakSeverity(Enum):
    """Severity levels for detected issues."""
    CRITICAL = "critical"  # Definite memory leak
    HIGH = "high"          # Very likely memory leak
    MEDIUM = "medium"      # Potential memory leak
    LOW = "low"            # Code smell, minor issue
    INFO = "info"          # Informational


class LeakType(Enum):
    """Types of memory leaks and issues."""
    STRONG_REFERENCE_CYCLE = "strong_reference_cycle"
    MISSING_WEAK_SELF = "missing_weak_self"
    NON_WEAK_DELEGATE = "non_weak_delegate"
    UNREMOVED_OBSERVER = "unremoved_observer"
    UNREMOVED_TIMER = "unremoved_timer"
    RETAIN_CYCLE_BLOCK = "retain_cycle_block"
    MISSING_DEALLOC = "missing_dealloc"
    MISSING_DEINIT = "missing_deinit"
    STRONG_IBOUTLET = "strong_iboutlet"
    CLOSURE_CAPTURE = "closure_capture"
    DISPATCH_ASYNC_SELF = "dispatch_async_self"
    ANIMATION_SELF = "animation_self"
    KVO_NOT_REMOVED = "kvo_not_removed"
    NOTIFICATION_NOT_REMOVED = "notification_not_removed"
    SINGLETON_STRONG_REF = "singleton_strong_ref"
    COLLECTION_STRONG_REF = "collection_strong_ref"
    MAIN_THREAD_HANG = "main_thread_hang"
    HEAVY_COMPUTATION_MAIN = "heavy_computation_main"
    SYNC_MAIN_DISPATCH = "sync_main_dispatch"


@dataclass
class FixSuggestion:
    """Represents a code fix suggestion."""
    original_code: str = ""
    fixed_code: str = ""
    description: str = ""
    start_line: int = 0
    end_line: int = 0
    start_column: int = 0
    end_column: int = 0
    is_auto_fixable: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original": self.original_code,
            "fixed": self.fixed_code,
            "description": self.description,
            "location": {
                "start_line": self.start_line,
                "end_line": self.end_line,
                "start_column": self.start_column,
                "end_column": self.end_column
            },
            "auto_fixable": self.is_auto_fixable
        }


@dataclass
class LeakPattern:
    """Represents a detected memory leak pattern."""
    type: LeakType
    severity: LeakSeverity
    file_path: str
    line_number: int
    column: int = 0
    end_line: int = 0
    end_column: int = 0
    code_snippet: str = ""
    message: str = ""
    suggestion: str = ""
    fix: Optional[FixSuggestion] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": self.type.value,
            "severity": self.severity.value,
            "file": self.file_path,
            "location": {
                "line": self.line_number,
                "column": self.column,
                "end_line": self.end_line or self.line_number,
                "end_column": self.end_column
            },
            "code": self.code_snippet,
            "message": self.message,
            "suggestion": self.suggestion,
            "context": self.context
        }
        if self.fix:
            result["fix"] = self.fix.to_dict()
        return result


# ===== Fix Generator Functions =====

def fix_missing_weak_self_swift(match_text: str, context: Dict) -> FixSuggestion:
    """Generate fix for missing [weak self] in Swift closure."""
    # Find where to insert [weak self]
    if '{ ' in match_text:
        fixed = match_text.replace('{ ', '{ [weak self] in ', 1)
    elif '{' in match_text:
        fixed = match_text.replace('{', '{ [weak self] in', 1)
    else:
        fixed = match_text

    # Also change self. to self?.
    fixed = re.sub(r'\bself\.', 'self?.', fixed)

    return FixSuggestion(
        original_code=match_text,
        fixed_code=fixed,
        description="Add [weak self] capture list and use optional chaining",
        is_auto_fixable=True
    )


def fix_non_weak_delegate_swift(match_text: str, context: Dict) -> FixSuggestion:
    """Generate fix for non-weak delegate in Swift."""
    # var delegate: -> weak var delegate:
    fixed = re.sub(r'\bvar\s+(\w*[Dd]elegate\w*)\s*:', r'weak var \1:', match_text)

    return FixSuggestion(
        original_code=match_text,
        fixed_code=fixed,
        description="Add 'weak' keyword to delegate property",
        is_auto_fixable=True
    )


def fix_strong_iboutlet_swift(match_text: str, context: Dict) -> FixSuggestion:
    """Generate fix for strong IBOutlet in Swift."""
    fixed = match_text.replace('@IBOutlet var', '@IBOutlet weak var')
    fixed = fixed.replace('@IBOutlet private var', '@IBOutlet private weak var')

    return FixSuggestion(
        original_code=match_text,
        fixed_code=fixed,
        description="Add 'weak' to IBOutlet property",
        is_auto_fixable=True
    )


def fix_dispatch_async_self_swift(match_text: str, context: Dict) -> FixSuggestion:
    """Generate fix for dispatch_async capturing self."""
    if '{ ' in match_text:
        fixed = match_text.replace('{ ', '{ [weak self] in ', 1)
    elif '{' in match_text:
        fixed = match_text.replace('{', '{ [weak self] in', 1)
    else:
        fixed = match_text

    fixed = re.sub(r'\bself\.', 'self?.', fixed)

    return FixSuggestion(
        original_code=match_text,
        fixed_code=fixed,
        description="Add [weak self] to dispatch block",
        is_auto_fixable=True
    )


def fix_block_self_capture_objc(match_text: str, context: Dict) -> FixSuggestion:
    """Generate fix for Objective-C block capturing self."""
    # Need to add __weak typeof(self) weakSelf = self; before block
    weak_declaration = "__weak typeof(self) weakSelf = self;\n    "

    # Replace self with weakSelf in block
    fixed_block = re.sub(r'\bself\b', 'weakSelf', match_text)

    return FixSuggestion(
        original_code=match_text,
        fixed_code=weak_declaration + fixed_block,
        description="Add __weak self declaration and use weakSelf in block",
        is_auto_fixable=True
    )


def fix_non_weak_delegate_objc(match_text: str, context: Dict) -> FixSuggestion:
    """Generate fix for non-weak delegate in Objective-C."""
    # @property (nonatomic, strong) -> @property (nonatomic, weak)
    fixed = re.sub(r'@property\s*\(([^)]*)\bstrong\b', r'@property (\1weak', match_text)
    fixed = re.sub(r'@property\s*\(([^)]*)\bretain\b', r'@property (\1weak', fixed)

    # If no memory attribute, add weak
    if 'weak' not in fixed and 'assign' not in fixed:
        fixed = re.sub(r'@property\s*\(([^)]*)\)', r'@property (\1, weak)', fixed)
        fixed = fixed.replace(', ,', ',').replace('(,', '(')

    return FixSuggestion(
        original_code=match_text,
        fixed_code=fixed,
        description="Change delegate property to weak",
        is_auto_fixable=True
    )


def fix_strong_iboutlet_objc(match_text: str, context: Dict) -> FixSuggestion:
    """Generate fix for strong IBOutlet in Objective-C."""
    fixed = re.sub(r'@property\s*\(([^)]*)\bstrong\b', r'@property (\1weak', match_text)

    return FixSuggestion(
        original_code=match_text,
        fixed_code=fixed,
        description="Change IBOutlet to weak",
        is_auto_fixable=True
    )


def fix_combine_sink_no_store(match_text: str, context: Dict) -> FixSuggestion:
    """Generate fix for Combine sink without store."""
    if '.store(in:' not in match_text:
        fixed = match_text.rstrip() + '\n            .store(in: &cancellables)'
    else:
        fixed = match_text

    return FixSuggestion(
        original_code=match_text,
        fixed_code=fixed,
        description="Add .store(in: &cancellables) to retain subscription",
        is_auto_fixable=True
    )


def fix_sync_main_dispatch(match_text: str, context: Dict) -> FixSuggestion:
    """Generate fix for synchronous main dispatch."""
    fixed = match_text.replace('.sync', '.async')

    return FixSuggestion(
        original_code=match_text,
        fixed_code=fixed,
        description="Change sync to async to avoid potential deadlock",
        is_auto_fixable=True
    )


# ===== Swift Patterns =====

SWIFT_PATTERNS = {
    # Closure without [weak self] or [unowned self]
    "closure_self_capture": {
        "pattern": r'\{\s*(?!\[(?:weak|unowned)\s+self\]).*?\bself\.',
        "type": LeakType.MISSING_WEAK_SELF,
        "severity": LeakSeverity.HIGH,
        "message": "Closure captures 'self' strongly without [weak self] or [unowned self]",
        "suggestion": "Add [weak self] at the beginning of the closure and use 'self?' or 'guard let self = self else { return }'",
        "fix_generator": fix_missing_weak_self_swift,
        "fix_example": {
            "before": "completionHandler = {\n    self.updateUI()\n}",
            "after": "completionHandler = { [weak self] in\n    self?.updateUI()\n}"
        }
    },

    # Non-weak delegate
    "non_weak_delegate": {
        "pattern": r'(?<!weak\s)var\s+\w*[Dd]elegate\w*\s*:\s*\w+\??',
        "type": LeakType.NON_WEAK_DELEGATE,
        "severity": LeakSeverity.HIGH,
        "message": "Delegate property is not declared as weak - creates strong reference cycle",
        "suggestion": "Declare delegate as 'weak var delegate: DelegateProtocol?'",
        "fix_generator": fix_non_weak_delegate_swift,
        "fix_example": {
            "before": "var delegate: MyDelegate?",
            "after": "weak var delegate: MyDelegate?"
        }
    },

    # Strong IBOutlet (should be weak)
    "strong_iboutlet": {
        "pattern": r'@IBOutlet\s+(?!weak\s)(?:private\s+)?var\s+\w+\s*:',
        "type": LeakType.STRONG_IBOUTLET,
        "severity": LeakSeverity.MEDIUM,
        "message": "IBOutlet is not declared as weak - may cause retain cycle with view hierarchy",
        "suggestion": "Use '@IBOutlet weak var' for view outlets",
        "fix_generator": fix_strong_iboutlet_swift,
        "fix_example": {
            "before": "@IBOutlet var headerLabel: UILabel!",
            "after": "@IBOutlet weak var headerLabel: UILabel!"
        }
    },

    # Timer without invalidation tracking
    "timer_creation": {
        "pattern": r'Timer\.(scheduledTimer|init)\s*\([^)]*\)\s*\{[^}]*\bself\.',
        "type": LeakType.UNREMOVED_TIMER,
        "severity": LeakSeverity.HIGH,
        "message": "Timer closure captures self strongly - will prevent deallocation",
        "suggestion": "Use [weak self] in timer closure and invalidate in deinit",
        "fix_generator": fix_missing_weak_self_swift,
        "fix_example": {
            "before": "Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { _ in\n    self.tick()\n}",
            "after": "Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in\n    self?.tick()\n}"
        }
    },

    # NotificationCenter addObserver without remove
    "notification_observer": {
        "pattern": r'NotificationCenter\.default\.addObserver\s*\(',
        "type": LeakType.UNREMOVED_OBSERVER,
        "severity": LeakSeverity.MEDIUM,
        "message": "NotificationCenter observer added - ensure removal in deinit",
        "suggestion": "Remove observer in deinit: NotificationCenter.default.removeObserver(self)",
        "fix_example": {
            "before": "// No deinit or missing removeObserver",
            "after": "deinit {\n    NotificationCenter.default.removeObserver(self)\n}"
        }
    },

    # KVO observation
    "kvo_observation": {
        "pattern": r'\.observe\s*\(\s*\\',
        "type": LeakType.KVO_NOT_REMOVED,
        "severity": LeakSeverity.MEDIUM,
        "message": "KVO observation added - store token and invalidate",
        "suggestion": "Store the observation token and set it to nil in deinit",
        "fix_example": {
            "before": "object.observe(\\.property) { ... }",
            "after": "observation = object.observe(\\.property) { ... }\n// In deinit: observation = nil"
        }
    },

    # DispatchQueue.main.async with self
    "dispatch_async_self": {
        "pattern": r'DispatchQueue\.\w+\.async\s*\{\s*(?!\[weak\s+self\]).*?\bself\.',
        "type": LeakType.DISPATCH_ASYNC_SELF,
        "severity": LeakSeverity.MEDIUM,
        "message": "Dispatch async block captures self strongly - may extend object lifetime",
        "suggestion": "Use [weak self] in dispatch blocks",
        "fix_generator": fix_dispatch_async_self_swift,
        "fix_example": {
            "before": "DispatchQueue.main.async {\n    self.updateUI()\n}",
            "after": "DispatchQueue.main.async { [weak self] in\n    self?.updateUI()\n}"
        }
    },

    # UIView.animate with self
    "animation_self": {
        "pattern": r'UIView\.animate\s*\([^)]*\)\s*\{\s*(?!\[weak\s+self\]).*?\bself\.',
        "type": LeakType.ANIMATION_SELF,
        "severity": LeakSeverity.LOW,
        "message": "Animation block captures self (usually OK but check for long animations)",
        "suggestion": "Consider [weak self] if animation is long-running or repeating",
        "fix_example": {
            "before": "UIView.animate(withDuration: 1.0) {\n    self.view.alpha = 0\n}",
            "after": "UIView.animate(withDuration: 1.0) { [weak self] in\n    self?.view.alpha = 0\n}"
        }
    },

    # Strong reference in closure stored property
    "stored_closure_self": {
        "pattern": r'(?:let|var)\s+\w+\s*:\s*\([^)]*\)\s*->\s*[^=]+\s*=\s*\{[^}]*\bself\.',
        "type": LeakType.CLOSURE_CAPTURE,
        "severity": LeakSeverity.HIGH,
        "message": "Stored closure property captures self strongly - definite retain cycle",
        "suggestion": "Use [weak self] or [unowned self] in the closure",
        "fix_generator": fix_missing_weak_self_swift,
        "fix_example": {
            "before": "var handler: () -> Void = {\n    self.doSomething()\n}",
            "after": "var handler: () -> Void = { [weak self] in\n    self?.doSomething()\n}"
        }
    },

    # Singleton with strong reference
    "singleton_strong": {
        "pattern": r'static\s+(?:let|var)\s+shared\s*[=:][^}]+\bself\b',
        "type": LeakType.SINGLETON_STRONG_REF,
        "severity": LeakSeverity.HIGH,
        "message": "Singleton may hold strong reference to self",
        "suggestion": "Avoid storing self in singleton; use weak references",
        "fix_example": {
            "before": "SomeManager.shared.callback = { self.handle() }",
            "after": "SomeManager.shared.callback = { [weak self] in self?.handle() }"
        }
    },
}

# ===== Objective-C Patterns =====

OBJC_PATTERNS = {
    # Block capturing self without __weak
    "block_self_capture": {
        "pattern": r'\^[^{]*\{[^}]*\bself\b',
        "type": LeakType.RETAIN_CYCLE_BLOCK,
        "severity": LeakSeverity.HIGH,
        "message": "Block captures 'self' without __weak - potential retain cycle",
        "suggestion": "Use __weak typeof(self) weakSelf = self; before block and use weakSelf inside",
        "fix_generator": fix_block_self_capture_objc,
        "fix_example": {
            "before": "self.completionBlock = ^{\n    [self updateUI];\n};",
            "after": "__weak typeof(self) weakSelf = self;\nself.completionBlock = ^{\n    [weakSelf updateUI];\n};"
        }
    },

    # Non-weak delegate property
    "non_weak_delegate_objc": {
        "pattern": r'@property\s*\([^)]*(?:strong|retain)[^)]*\)\s*[^;]*[Dd]elegate[^;]*;',
        "type": LeakType.NON_WEAK_DELEGATE,
        "severity": LeakSeverity.HIGH,
        "message": "Delegate property is strong/retain - creates retain cycle",
        "suggestion": "Use @property (nonatomic, weak) for delegate properties",
        "fix_generator": fix_non_weak_delegate_objc,
        "fix_example": {
            "before": "@property (nonatomic, strong) id<MyDelegate> delegate;",
            "after": "@property (nonatomic, weak) id<MyDelegate> delegate;"
        }
    },

    # Strong IBOutlet
    "strong_iboutlet_objc": {
        "pattern": r'@property\s*\([^)]*strong[^)]*\)\s*IBOutlet',
        "type": LeakType.STRONG_IBOUTLET,
        "severity": LeakSeverity.MEDIUM,
        "message": "IBOutlet should typically be weak",
        "suggestion": "Use @property (nonatomic, weak) IBOutlet for view outlets",
        "fix_generator": fix_strong_iboutlet_objc,
        "fix_example": {
            "before": "@property (nonatomic, strong) IBOutlet UILabel *titleLabel;",
            "after": "@property (nonatomic, weak) IBOutlet UILabel *titleLabel;"
        }
    },

    # NSTimer creation
    "nstimer_creation": {
        "pattern": r'\[NSTimer\s+scheduledTimerWithTimeInterval:[^]]*target:\s*self',
        "type": LeakType.UNREMOVED_TIMER,
        "severity": LeakSeverity.HIGH,
        "message": "NSTimer retains target (self) - prevents deallocation until invalidated",
        "suggestion": "Use block-based timer API (iOS 10+) with weakSelf, or invalidate in dealloc",
        "fix_example": {
            "before": "[NSTimer scheduledTimerWithTimeInterval:1.0 target:self selector:@selector(tick) userInfo:nil repeats:YES];",
            "after": "__weak typeof(self) weakSelf = self;\n[NSTimer scheduledTimerWithTimeInterval:1.0 repeats:YES block:^(NSTimer *timer) {\n    [weakSelf tick];\n}];"
        }
    },

    # NSNotificationCenter observer
    "notification_observer_objc": {
        "pattern": r'\[\[NSNotificationCenter\s+defaultCenter\]\s+addObserver:\s*self',
        "type": LeakType.NOTIFICATION_NOT_REMOVED,
        "severity": LeakSeverity.MEDIUM,
        "message": "NotificationCenter observer added - must remove in dealloc",
        "suggestion": "Add [[NSNotificationCenter defaultCenter] removeObserver:self] in dealloc",
        "fix_example": {
            "before": "// No dealloc or missing removeObserver",
            "after": "- (void)dealloc {\n    [[NSNotificationCenter defaultCenter] removeObserver:self];\n}"
        }
    },

    # KVO observation
    "kvo_objc": {
        "pattern": r'\[\s*\w+\s+addObserver:\s*self\s+forKeyPath:',
        "type": LeakType.KVO_NOT_REMOVED,
        "severity": LeakSeverity.HIGH,
        "message": "KVO observer added - must remove in dealloc or will crash",
        "suggestion": "Call [object removeObserver:self forKeyPath:...] in dealloc",
        "fix_example": {
            "before": "[self.someObject addObserver:self forKeyPath:@\"property\" options:0 context:nil];",
            "after": "// In dealloc:\n[self.someObject removeObserver:self forKeyPath:@\"property\"];"
        }
    },

    # dispatch_async with self
    "dispatch_async_objc": {
        "pattern": r'dispatch_async\s*\([^,]+,\s*\^[^{]*\{[^}]*\bself\b',
        "type": LeakType.DISPATCH_ASYNC_SELF,
        "severity": LeakSeverity.MEDIUM,
        "message": "dispatch_async block captures self strongly",
        "suggestion": "Use __weak typeof(self) weakSelf = self; before block",
        "fix_generator": fix_block_self_capture_objc,
        "fix_example": {
            "before": "dispatch_async(dispatch_get_main_queue(), ^{\n    [self updateUI];\n});",
            "after": "__weak typeof(self) weakSelf = self;\ndispatch_async(dispatch_get_main_queue(), ^{\n    [weakSelf updateUI];\n});"
        }
    },

    # Missing dealloc
    "missing_dealloc": {
        "pattern": r'@implementation\s+\w+(?:(?!-\s*\(void\)\s*dealloc).)*@end',
        "type": LeakType.MISSING_DEALLOC,
        "severity": LeakSeverity.INFO,
        "message": "Class doesn't implement dealloc - add for debugging and cleanup",
        "suggestion": "Add -(void)dealloc { NSLog(@\"%@ deallocated\", self); } for debugging",
        "fix_example": {
            "before": "@implementation MyClass\n// ... methods ...\n@end",
            "after": "@implementation MyClass\n// ... methods ...\n\n- (void)dealloc {\n    // Cleanup code here\n    NSLog(@\"%@ deallocated\", NSStringFromClass([self class]));\n}\n\n@end"
        }
    },
}

# ===== SwiftUI Patterns =====

SWIFTUI_PATTERNS = {
    # ObservableObject without @Published
    "observable_no_published": {
        "pattern": r'class\s+\w+\s*:\s*ObservableObject\s*\{(?:(?!@Published).)*\bvar\s+\w+',
        "type": LeakType.STRONG_REFERENCE_CYCLE,
        "severity": LeakSeverity.INFO,
        "message": "ObservableObject property without @Published won't trigger view updates",
        "suggestion": "Use @Published for properties that should update views",
        "fix_example": {
            "before": "class ViewModel: ObservableObject {\n    var items: [String] = []\n}",
            "after": "class ViewModel: ObservableObject {\n    @Published var items: [String] = []\n}"
        }
    },

    # ViewModel with strong self in closure
    "viewmodel_closure_self": {
        "pattern": r'class\s+\w*ViewModel[^{]*\{[^}]*\.\s*sink\s*\{[^}]*\bself\.',
        "type": LeakType.MISSING_WEAK_SELF,
        "severity": LeakSeverity.HIGH,
        "message": "ViewModel Combine sink captures self strongly - retain cycle!",
        "suggestion": "Use [weak self] in ViewModel closures and Combine sinks",
        "fix_generator": fix_missing_weak_self_swift,
        "fix_example": {
            "before": ".sink { _ in\n    self.tick()\n}",
            "after": ".sink { [weak self] _ in\n    self?.tick()\n}"
        }
    },

    # Timer in SwiftUI without cancellation
    "swiftui_timer": {
        "pattern": r'Timer\.publish\s*\([^)]*\)\s*\.\s*autoconnect\s*\(\s*\)',
        "type": LeakType.UNREMOVED_TIMER,
        "severity": LeakSeverity.LOW,
        "message": "Timer publisher in SwiftUI - ensure proper lifecycle management",
        "suggestion": "Store in @State and use .onReceive() or .task modifier",
        "fix_example": {
            "before": "let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()",
            "after": "@State private var timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()\n// Use with .onReceive(timer) { _ in ... }"
        }
    },

    # Combine sink without storing cancellable
    "combine_sink_no_store": {
        "pattern": r'\.sink\s*\{[^}]+\}(?!\s*\.\s*store)',
        "type": LeakType.UNREMOVED_OBSERVER,
        "severity": LeakSeverity.HIGH,
        "message": "Combine sink without .store() - subscription will be immediately cancelled",
        "suggestion": "Store the cancellable: .sink {...}.store(in: &cancellables)",
        "fix_generator": fix_combine_sink_no_store,
        "fix_example": {
            "before": "publisher.sink { value in\n    print(value)\n}",
            "after": "publisher.sink { value in\n    print(value)\n}\n.store(in: &cancellables)"
        }
    },

    # URLSession in View body
    "network_in_body": {
        "pattern": r'var\s+body\s*:\s*some\s+View\s*\{[^}]*URLSession',
        "type": LeakType.MAIN_THREAD_HANG,
        "severity": LeakSeverity.HIGH,
        "message": "Network call in View body - blocks main thread on every redraw",
        "suggestion": "Move network calls to .task modifier or .onAppear",
        "fix_example": {
            "before": "var body: some View {\n    let data = URLSession.shared.data(from: url)\n    // ...\n}",
            "after": "var body: some View {\n    Content()\n        .task {\n            let data = try? await URLSession.shared.data(from: url)\n        }\n}"
        }
    },

    # Heavy computation in View body
    "heavy_body_computation": {
        "pattern": r'var\s+body\s*:\s*some\s+View\s*\{[^}]*\b(?:for|while)\s+[^}]*in\s+',
        "type": LeakType.MAIN_THREAD_HANG,
        "severity": LeakSeverity.HIGH,
        "message": "Loop in View body - recalculates on every view update",
        "suggestion": "Extract to @State, computed property, or cache in ViewModel",
        "fix_example": {
            "before": "var body: some View {\n    let items = (0..<1000).map { $0 * 2 }\n    // ...\n}",
            "after": "@State private var items = (0..<1000).map { $0 * 2 }\n\nvar body: some View {\n    // Use items directly\n}"
        }
    },

    # Large image sync loading
    "large_image_sync": {
        "pattern": r'Image\s*\(\s*uiImage:\s*UIImage\s*\([^)]*named:',
        "type": LeakType.MAIN_THREAD_HANG,
        "severity": LeakSeverity.MEDIUM,
        "message": "Synchronous image loading in SwiftUI - may block UI",
        "suggestion": "Use AsyncImage or load images in background task",
        "fix_example": {
            "before": "Image(uiImage: UIImage(named: \"large_image\")!)",
            "after": "AsyncImage(url: imageURL) { image in\n    image.resizable()\n} placeholder: {\n    ProgressView()\n}"
        }
    },

    # Async task without cancellation check
    "async_task_no_cancel": {
        "pattern": r'\.task\s*\{[^}]*await(?:(?!Task\.checkCancellation|Task\.isCancelled|try\s+Task).)*\}',
        "type": LeakType.UNREMOVED_OBSERVER,
        "severity": LeakSeverity.LOW,
        "message": "Async task without cancellation check - may waste resources",
        "suggestion": "Check Task.isCancelled for long-running operations",
        "fix_example": {
            "before": ".task {\n    let data = await fetchData()\n    self.data = data\n}",
            "after": ".task {\n    guard !Task.isCancelled else { return }\n    let data = await fetchData()\n    guard !Task.isCancelled else { return }\n    self.data = data\n}"
        }
    },
}

# ===== Performance/Hang Patterns =====

PERFORMANCE_PATTERNS = {
    # Heavy computation on main thread
    "heavy_main_thread": {
        "pattern": r'DispatchQueue\.main\.[^}]*\b(for|while)\s+',
        "type": LeakType.HEAVY_COMPUTATION_MAIN,
        "severity": LeakSeverity.HIGH,
        "message": "Loop in main queue dispatch - will freeze UI",
        "suggestion": "Move heavy computation to background queue, update UI on main",
        "fix_example": {
            "before": "DispatchQueue.main.async {\n    for item in items {\n        process(item)\n    }\n}",
            "after": "DispatchQueue.global(qos: .userInitiated).async {\n    for item in items {\n        process(item)\n    }\n    DispatchQueue.main.async {\n        self.updateUI()\n    }\n}"
        }
    },

    # Synchronous main dispatch
    "sync_main_dispatch": {
        "pattern": r'DispatchQueue\.main\.sync\s*\{',
        "type": LeakType.SYNC_MAIN_DISPATCH,
        "severity": LeakSeverity.CRITICAL,
        "message": "Synchronous dispatch to main queue - WILL DEADLOCK if called from main",
        "suggestion": "Use DispatchQueue.main.async or check Thread.isMainThread first",
        "fix_generator": fix_sync_main_dispatch,
        "fix_example": {
            "before": "DispatchQueue.main.sync {\n    self.updateUI()\n}",
            "after": "DispatchQueue.main.async {\n    self.updateUI()\n}"
        }
    },

    # Image processing on main thread
    "image_processing_main": {
        "pattern": r'(?:UIImage|CGImage|CIImage)[^}]*\b(?:resize|scale|filter|draw)',
        "type": LeakType.MAIN_THREAD_HANG,
        "severity": LeakSeverity.MEDIUM,
        "message": "Image processing detected - ensure not blocking main thread",
        "suggestion": "Perform image processing on background queue",
        "fix_example": {
            "before": "let resized = image.resize(to: size)",
            "after": "DispatchQueue.global(qos: .userInitiated).async {\n    let resized = image.resize(to: size)\n    DispatchQueue.main.async {\n        self.imageView.image = resized\n    }\n}"
        }
    },

    # Synchronous network call
    "sync_network": {
        "pattern": r'URLSession[^}]*(?:dataTask|sendSynchronous)',
        "type": LeakType.MAIN_THREAD_HANG,
        "severity": LeakSeverity.HIGH,
        "message": "Potential synchronous network call detected",
        "suggestion": "Use async/await or completion handlers for network calls",
        "fix_example": {
            "before": "let data = try! Data(contentsOf: url)",
            "after": "Task {\n    let (data, _) = try await URLSession.shared.data(from: url)\n    // Handle data\n}"
        }
    },

    # File operations on main
    "file_io_main": {
        "pattern": r'(?:FileManager|NSFileManager)[^}]*\b(?:contents|write|move|copy|remove)(?:OfItem|AtPath)?',
        "type": LeakType.MAIN_THREAD_HANG,
        "severity": LeakSeverity.MEDIUM,
        "message": "File I/O operation - may block if files are large",
        "suggestion": "Perform file operations on background queue for large files",
        "fix_example": {
            "before": "let data = FileManager.default.contents(atPath: path)",
            "after": "DispatchQueue.global(qos: .utility).async {\n    let data = FileManager.default.contents(atPath: path)\n    DispatchQueue.main.async {\n        self.handleData(data)\n    }\n}"
        }
    },

    # Core Data on main
    "coredata_main": {
        "pattern": r'NSManagedObjectContext[^}]*(?:save|fetch|execute)',
        "type": LeakType.MAIN_THREAD_HANG,
        "severity": LeakSeverity.MEDIUM,
        "message": "Core Data operation - use background context for heavy operations",
        "suggestion": "Use container.performBackgroundTask for bulk operations",
        "fix_example": {
            "before": "let results = try context.fetch(request)",
            "after": "container.performBackgroundTask { context in\n    let results = try? context.fetch(request)\n    // Process in background\n}"
        }
    },
}


def get_all_patterns(language: str = "all") -> Dict[str, Dict]:
    """Get all patterns for specified language."""
    patterns = {}

    if language in ("swift", "all"):
        patterns.update(SWIFT_PATTERNS)
        patterns.update(PERFORMANCE_PATTERNS)

    if language in ("swiftui", "all"):
        patterns.update(SWIFTUI_PATTERNS)
        if language == "swiftui":
            patterns.update(SWIFT_PATTERNS)
            patterns.update(PERFORMANCE_PATTERNS)

    if language in ("objc", "objective-c", "all"):
        patterns.update(OBJC_PATTERNS)
        if language != "all":  # Avoid duplicates
            patterns.update(PERFORMANCE_PATTERNS)

    return patterns


def compile_patterns() -> Dict[str, re.Pattern]:
    """Compile all regex patterns."""
    compiled = {}
    all_patterns = get_all_patterns("all")

    for name, pattern_data in all_patterns.items():
        try:
            compiled[name] = re.compile(pattern_data["pattern"], re.MULTILINE | re.DOTALL)
        except re.error as e:
            print(f"Warning: Failed to compile pattern '{name}': {e}")

    return compiled


def get_fix_example(pattern_name: str) -> Optional[Dict[str, str]]:
    """Get fix example for a pattern."""
    all_patterns = get_all_patterns("all")
    if pattern_name in all_patterns:
        return all_patterns[pattern_name].get("fix_example")
    return None
