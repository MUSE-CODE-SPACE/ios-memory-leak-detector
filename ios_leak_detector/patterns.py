"""
Memory Leak Patterns and Detection Rules
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
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
class LeakPattern:
    """Represents a detected memory leak pattern."""
    type: LeakType
    severity: LeakSeverity
    file_path: str
    line_number: int
    column: int = 0
    code_snippet: str = ""
    message: str = ""
    suggestion: str = ""
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "severity": self.severity.value,
            "file": self.file_path,
            "line": self.line_number,
            "column": self.column,
            "code": self.code_snippet,
            "message": self.message,
            "suggestion": self.suggestion,
            "context": self.context
        }


# ===== Swift Patterns =====

SWIFT_PATTERNS = {
    # Closure without [weak self] or [unowned self]
    "closure_self_capture": {
        "pattern": r'\{\s*(?!\[(?:weak|unowned)\s+self\]).*?\bself\b',
        "type": LeakType.MISSING_WEAK_SELF,
        "severity": LeakSeverity.HIGH,
        "message": "Closure captures 'self' strongly without [weak self] or [unowned self]",
        "suggestion": "Add [weak self] at the beginning of the closure and use 'self?' or 'guard let self = self else { return }'"
    },

    # Non-weak delegate
    "non_weak_delegate": {
        "pattern": r'(?<!weak\s)var\s+\w*[Dd]elegate\w*\s*:',
        "type": LeakType.NON_WEAK_DELEGATE,
        "severity": LeakSeverity.HIGH,
        "message": "Delegate property is not declared as weak",
        "suggestion": "Declare delegate as 'weak var delegate: DelegateProtocol?'"
    },

    # Strong IBOutlet (should be weak)
    "strong_iboutlet": {
        "pattern": r'@IBOutlet\s+(?!weak\s)var\s+\w+\s*:',
        "type": LeakType.STRONG_IBOUTLET,
        "severity": LeakSeverity.MEDIUM,
        "message": "IBOutlet is not declared as weak",
        "suggestion": "Use '@IBOutlet weak var' for view outlets"
    },

    # Timer without invalidation tracking
    "timer_creation": {
        "pattern": r'Timer\.(scheduledTimer|init)\s*\(',
        "type": LeakType.UNREMOVED_TIMER,
        "severity": LeakSeverity.MEDIUM,
        "message": "Timer created - ensure it's invalidated in deinit",
        "suggestion": "Store timer reference and call timer.invalidate() in deinit"
    },

    # NotificationCenter addObserver without remove
    "notification_observer": {
        "pattern": r'NotificationCenter\.default\.addObserver\s*\(',
        "type": LeakType.UNREMOVED_OBSERVER,
        "severity": LeakSeverity.MEDIUM,
        "message": "NotificationCenter observer added - ensure removal in deinit",
        "suggestion": "Remove observer in deinit: NotificationCenter.default.removeObserver(self)"
    },

    # KVO observation
    "kvo_observation": {
        "pattern": r'\.observe\s*\(\s*\\',
        "type": LeakType.KVO_NOT_REMOVED,
        "severity": LeakSeverity.MEDIUM,
        "message": "KVO observation added - store token and invalidate",
        "suggestion": "Store the observation token and set it to nil in deinit"
    },

    # DispatchQueue.main.async with self
    "dispatch_async_self": {
        "pattern": r'DispatchQueue\.\w+\.async\s*\{\s*(?!\[weak\s+self\]).*?\bself\b',
        "type": LeakType.DISPATCH_ASYNC_SELF,
        "severity": LeakSeverity.MEDIUM,
        "message": "Dispatch async block captures self strongly",
        "suggestion": "Use [weak self] in dispatch blocks"
    },

    # UIView.animate with self
    "animation_self": {
        "pattern": r'UIView\.animate\s*\([^)]*\)\s*\{\s*(?!\[weak\s+self\]).*?\bself\b',
        "type": LeakType.ANIMATION_SELF,
        "severity": LeakSeverity.LOW,
        "message": "Animation block captures self (usually OK but check)",
        "suggestion": "Consider [weak self] if animation is long-running"
    },

    # Missing deinit in class
    "class_without_deinit": {
        "pattern": r'class\s+\w+[^{]*\{(?:(?!deinit\s*\{).)*\}',
        "type": LeakType.MISSING_DEINIT,
        "severity": LeakSeverity.INFO,
        "message": "Class doesn't have deinit - add for debugging memory issues",
        "suggestion": "Add deinit { print(\"\\(type(of: self)) deallocated\") } for debugging"
    },

    # Strong reference in closure stored property
    "stored_closure_self": {
        "pattern": r'(?:let|var)\s+\w+\s*:\s*\([^)]*\)\s*->\s*[^=]+\s*=\s*\{[^}]*\bself\b',
        "type": LeakType.CLOSURE_CAPTURE,
        "severity": LeakSeverity.HIGH,
        "message": "Stored closure property captures self strongly",
        "suggestion": "Use [weak self] or [unowned self] in the closure"
    },

    # Singleton with strong reference
    "singleton_strong": {
        "pattern": r'static\s+(?:let|var)\s+shared\s*[=:][^}]+\bself\b',
        "type": LeakType.SINGLETON_STRONG_REF,
        "severity": LeakSeverity.HIGH,
        "message": "Singleton may hold strong reference to self",
        "suggestion": "Avoid storing self in singleton; use weak references"
    },
}

# ===== Objective-C Patterns =====

OBJC_PATTERNS = {
    # Block capturing self without __weak
    "block_self_capture": {
        "pattern": r'\^[^{]*\{[^}]*\bself\b',
        "type": LeakType.RETAIN_CYCLE_BLOCK,
        "severity": LeakSeverity.HIGH,
        "message": "Block captures 'self' - potential retain cycle",
        "suggestion": "Use __weak typeof(self) weakSelf = self; before block and use weakSelf inside"
    },

    # Non-weak delegate property
    "non_weak_delegate_objc": {
        "pattern": r'@property\s*\([^)]*(?<!weak)[^)]*\)\s*\w+\s*\*?\s*\w*[Dd]elegate',
        "type": LeakType.NON_WEAK_DELEGATE,
        "severity": LeakSeverity.HIGH,
        "message": "Delegate property is not weak",
        "suggestion": "Use @property (nonatomic, weak) for delegate properties"
    },

    # Strong IBOutlet
    "strong_iboutlet_objc": {
        "pattern": r'@property\s*\([^)]*strong[^)]*\)\s*IBOutlet',
        "type": LeakType.STRONG_IBOUTLET,
        "severity": LeakSeverity.MEDIUM,
        "message": "IBOutlet should typically be weak",
        "suggestion": "Use @property (nonatomic, weak) IBOutlet for view outlets"
    },

    # Missing dealloc
    "missing_dealloc": {
        "pattern": r'@implementation\s+\w+(?:(?!-\s*\(void\)\s*dealloc).)*@end',
        "type": LeakType.MISSING_DEALLOC,
        "severity": LeakSeverity.INFO,
        "message": "Class doesn't implement dealloc",
        "suggestion": "Add -(void)dealloc { NSLog(@\"%@ deallocated\", self); } for debugging"
    },

    # NSTimer creation
    "nstimer_creation": {
        "pattern": r'\[NSTimer\s+scheduledTimer',
        "type": LeakType.UNREMOVED_TIMER,
        "severity": LeakSeverity.MEDIUM,
        "message": "NSTimer created - ensure invalidation in dealloc",
        "suggestion": "Store timer and call [timer invalidate] in dealloc"
    },

    # NSNotificationCenter observer
    "notification_observer_objc": {
        "pattern": r'\[\[NSNotificationCenter\s+defaultCenter\]\s+addObserver',
        "type": LeakType.NOTIFICATION_NOT_REMOVED,
        "severity": LeakSeverity.MEDIUM,
        "message": "NotificationCenter observer added - remove in dealloc",
        "suggestion": "Add [[NSNotificationCenter defaultCenter] removeObserver:self] in dealloc"
    },

    # KVO observation
    "kvo_objc": {
        "pattern": r'addObserver:\s*self\s+forKeyPath:',
        "type": LeakType.KVO_NOT_REMOVED,
        "severity": LeakSeverity.HIGH,
        "message": "KVO observer added - must remove in dealloc",
        "suggestion": "Call removeObserver:forKeyPath: in dealloc"
    },

    # dispatch_async with self
    "dispatch_async_objc": {
        "pattern": r'dispatch_async\s*\([^,]+,\s*\^[^{]*\{[^}]*\bself\b',
        "type": LeakType.DISPATCH_ASYNC_SELF,
        "severity": LeakSeverity.MEDIUM,
        "message": "dispatch_async block captures self strongly",
        "suggestion": "Use __weak typeof(self) weakSelf = self; before block"
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
        "suggestion": "Use @Published for properties that should update views"
    },

    # Strong reference in View's closure
    "view_closure_self": {
        "pattern": r'(?:Button|onTapGesture|onAppear|onDisappear|task|onChange)\s*\{[^}]*\bself\b',
        "type": LeakType.CLOSURE_CAPTURE,
        "severity": LeakSeverity.LOW,
        "message": "SwiftUI View closure references self (usually OK for structs)",
        "suggestion": "If using class-based ViewModel, ensure [weak self]"
    },

    # EnvironmentObject without @EnvironmentObject
    "environment_object_missing": {
        "pattern": r'\bEnvironmentObject<\w+>\s*\(\s*\)',
        "type": LeakType.STRONG_REFERENCE_CYCLE,
        "severity": LeakSeverity.MEDIUM,
        "message": "EnvironmentObject access pattern detected",
        "suggestion": "Ensure parent view provides the environment object"
    },

    # StateObject in non-View struct
    "stateobject_wrong_context": {
        "pattern": r'(?<!View\s)\{[^}]*@StateObject',
        "type": LeakType.STRONG_REFERENCE_CYCLE,
        "severity": LeakSeverity.MEDIUM,
        "message": "@StateObject used in potentially wrong context",
        "suggestion": "@StateObject should only be used in View structs"
    },

    # ObservedObject with strong reference cycle risk
    "observed_object_cycle": {
        "pattern": r'@ObservedObject\s+var\s+\w+\s*:\s*\w+\s*\{',
        "type": LeakType.STRONG_REFERENCE_CYCLE,
        "severity": LeakSeverity.MEDIUM,
        "message": "@ObservedObject with computed property may cause issues",
        "suggestion": "Use @StateObject for owned objects, @ObservedObject for passed objects"
    },

    # Timer in SwiftUI without cancellation
    "swiftui_timer": {
        "pattern": r'Timer\.publish\s*\(',
        "type": LeakType.UNREMOVED_TIMER,
        "severity": LeakSeverity.LOW,
        "message": "Timer publisher in SwiftUI - ensure proper lifecycle",
        "suggestion": "Store in @State and use .onReceive() or .task with cancellation"
    },

    # Combine sink without storing cancellable
    "combine_sink_no_store": {
        "pattern": r'\.sink\s*\{[^}]*\}[^.]*(?!\s*\.store)',
        "type": LeakType.UNREMOVED_OBSERVER,
        "severity": LeakSeverity.HIGH,
        "message": "Combine sink without storing cancellable - subscription won't persist",
        "suggestion": "Store the cancellable: .sink {...}.store(in: &cancellables)"
    },

    # ViewModel with strong self in closure
    "viewmodel_closure_self": {
        "pattern": r'class\s+\w*ViewModel[^{]*\{[^}]*\{\s*(?!\[weak\s+self\]).*?\bself\b',
        "type": LeakType.MISSING_WEAK_SELF,
        "severity": LeakSeverity.HIGH,
        "message": "ViewModel closure captures self strongly",
        "suggestion": "Use [weak self] in ViewModel closures"
    },

    # URLSession.shared in View body
    "network_in_body": {
        "pattern": r'var\s+body\s*:\s*some\s+View\s*\{[^}]*URLSession',
        "type": LeakType.MAIN_THREAD_HANG,
        "severity": LeakSeverity.HIGH,
        "message": "Network call in View body property",
        "suggestion": "Move network calls to .task or .onAppear"
    },

    # Heavy computation in View body
    "heavy_body_computation": {
        "pattern": r'var\s+body\s*:\s*some\s+View\s*\{[^}]*\b(?:for|while)\s+',
        "type": LeakType.MAIN_THREAD_HANG,
        "severity": LeakSeverity.HIGH,
        "message": "Loop in View body - causes unnecessary recomputation",
        "suggestion": "Extract computed value to @State or cached property"
    },

    # Async/await without Task cancellation
    "async_task_no_cancel": {
        "pattern": r'\.task\s*\{[^}]*await(?:(?!Task\.checkCancellation|Task\.isCancelled).)*\}',
        "type": LeakType.UNREMOVED_OBSERVER,
        "severity": LeakSeverity.LOW,
        "message": "Async task without cancellation check",
        "suggestion": "Check Task.isCancelled for long-running tasks"
    },

    # Large image in View without async loading
    "large_image_sync": {
        "pattern": r'Image\s*\(\s*(?:uiImage:|nsImage:)\s*UIImage\s*\(',
        "type": LeakType.MAIN_THREAD_HANG,
        "severity": LeakSeverity.MEDIUM,
        "message": "Synchronous image loading in SwiftUI View",
        "suggestion": "Use AsyncImage or load images in background"
    },
}

# ===== Performance/Hang Patterns =====

PERFORMANCE_PATTERNS = {
    # Heavy computation on main thread
    "heavy_main_thread": {
        "pattern": r'DispatchQueue\.main\.[^}]*\b(for|while)\s+',
        "type": LeakType.HEAVY_COMPUTATION_MAIN,
        "severity": LeakSeverity.HIGH,
        "message": "Loop in main queue dispatch - may cause UI hang",
        "suggestion": "Move heavy computation to background queue"
    },

    # Synchronous main dispatch
    "sync_main_dispatch": {
        "pattern": r'DispatchQueue\.main\.sync',
        "type": LeakType.SYNC_MAIN_DISPATCH,
        "severity": LeakSeverity.CRITICAL,
        "message": "Synchronous dispatch to main queue - can cause deadlock",
        "suggestion": "Use DispatchQueue.main.async instead, or check if already on main thread"
    },

    # Large image processing on main
    "image_processing_main": {
        "pattern": r'(?:UIImage|CGImage|CIImage)[^}]*\b(?:resize|scale|filter|draw)',
        "type": LeakType.MAIN_THREAD_HANG,
        "severity": LeakSeverity.MEDIUM,
        "message": "Image processing detected - ensure not on main thread",
        "suggestion": "Move image processing to background queue"
    },

    # Synchronous network call
    "sync_network": {
        "pattern": r'(?:URLSession|NSURLConnection)[^}]*(?:dataTask|sendSynchronous)',
        "type": LeakType.MAIN_THREAD_HANG,
        "severity": LeakSeverity.HIGH,
        "message": "Potential synchronous network call",
        "suggestion": "Use async network calls with completion handlers"
    },

    # File operations on main
    "file_io_main": {
        "pattern": r'(?:FileManager|NSFileManager)[^}]*\b(?:contents|write|move|copy|remove)',
        "type": LeakType.MAIN_THREAD_HANG,
        "severity": LeakSeverity.MEDIUM,
        "message": "File I/O operation detected - check if on background thread",
        "suggestion": "Perform file operations on background queue"
    },

    # Core Data on main
    "coredata_main": {
        "pattern": r'NSManagedObjectContext[^}]*(?:save|fetch|execute)',
        "type": LeakType.MAIN_THREAD_HANG,
        "severity": LeakSeverity.MEDIUM,
        "message": "Core Data operation - ensure using background context for heavy operations",
        "suggestion": "Use performBackgroundTask for heavy Core Data operations"
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
