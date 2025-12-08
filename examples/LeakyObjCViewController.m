// Example Objective-C file with common memory leak patterns
// Used for testing ios-leak-detector

#import "LeakyObjCViewController.h"

@interface LeakyObjCViewController ()

// ❌ Non-weak delegate
@property (nonatomic, strong) id<MyObjCDelegate> delegate;

// ❌ Strong IBOutlet
@property (nonatomic, strong) IBOutlet UILabel *titleLabel;

// ✅ Correct - weak IBOutlet
@property (nonatomic, weak) IBOutlet UILabel *subtitleLabel;

@property (nonatomic, strong) NSTimer *timer;
@property (nonatomic, copy) void (^completionBlock)(void);

@end

@implementation LeakyObjCViewController

- (void)viewDidLoad {
    [super viewDidLoad];

    // ❌ Block captures self without __weak - RETAIN CYCLE!
    self.completionBlock = ^{
        [self updateUI];
    };

    // ❌ Timer captures self strongly
    self.timer = [NSTimer scheduledTimerWithTimeInterval:1.0
                                                  target:self
                                                selector:@selector(tick)
                                                userInfo:nil
                                                 repeats:YES];

    // ❌ NotificationCenter observer without removal
    [[NSNotificationCenter defaultCenter] addObserver:self
                                             selector:@selector(handleNotification:)
                                                 name:@"SomeNotification"
                                               object:nil];

    // ❌ KVO observer without removal
    [self.someObject addObserver:self
                      forKeyPath:@"someProperty"
                         options:NSKeyValueObservingOptionNew
                         context:nil];

    // ❌ dispatch_async captures self
    dispatch_async(dispatch_get_main_queue(), ^{
        [self updateUI];
    });
}

- (void)handleNotification:(NSNotification *)notification {
    NSLog(@"Notification received");
}

- (void)observeValueForKeyPath:(NSString *)keyPath
                      ofObject:(id)object
                        change:(NSDictionary *)change
                       context:(void *)context {
    NSLog(@"KVO change: %@", change);
}

- (void)tick {
    NSLog(@"Timer tick");
}

- (void)updateUI {
    self.titleLabel.text = @"Updated";
}

// ❌ No dealloc method - can't verify cleanup!

@end


// ===== FIXED VERSION =====

@interface FixedObjCViewController ()

// ✅ Weak delegate
@property (nonatomic, weak) id<MyObjCDelegate> delegate;

// ✅ Weak IBOutlet
@property (nonatomic, weak) IBOutlet UILabel *titleLabel;

@property (nonatomic, strong) NSTimer *timer;
@property (nonatomic, copy) void (^completionBlock)(void);

@end

@implementation FixedObjCViewController

- (void)viewDidLoad {
    [super viewDidLoad];

    // ✅ Block with __weak self
    __weak typeof(self) weakSelf = self;
    self.completionBlock = ^{
        [weakSelf updateUI];
    };

    // ✅ Timer with weak reference via block API (iOS 10+)
    __weak typeof(self) weakTimer = self;
    self.timer = [NSTimer scheduledTimerWithTimeInterval:1.0
                                                 repeats:YES
                                                   block:^(NSTimer *timer) {
        [weakTimer tick];
    }];

    // ✅ Observer - will be removed in dealloc
    [[NSNotificationCenter defaultCenter] addObserver:self
                                             selector:@selector(handleNotification:)
                                                 name:@"SomeNotification"
                                               object:nil];

    // ✅ dispatch_async with weak self
    __weak typeof(self) weakDispatch = self;
    dispatch_async(dispatch_get_main_queue(), ^{
        [weakDispatch updateUI];
    });
}

- (void)handleNotification:(NSNotification *)notification {
    NSLog(@"Notification received");
}

- (void)tick {
    NSLog(@"Timer tick");
}

- (void)updateUI {
    self.titleLabel.text = @"Updated";
}

// ✅ Proper cleanup in dealloc
- (void)dealloc {
    [self.timer invalidate];
    self.timer = nil;
    [[NSNotificationCenter defaultCenter] removeObserver:self];
    NSLog(@"%@ deallocated", NSStringFromClass([self class]));
}

@end
