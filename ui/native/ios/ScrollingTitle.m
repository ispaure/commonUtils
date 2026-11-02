#import <UIKit/UIKit.h>
#import <QuartzCore/QuartzCore.h>

// Keep the label's frame (and the header's hold target) still. Only the ink moves.
@interface CommonUtilsPanningTitle : UILabel
@property(nonatomic, strong) UILabel *movingText;
@property(nonatomic) CGFloat travel;
@property(nonatomic) BOOL startsAtRight;
@end

@implementation CommonUtilsPanningTitle
- (instancetype)initWithFrame:(CGRect)frame {
    self = [super initWithFrame:frame];
    if (self) {
        if (@available(iOS 17.0, *)) {
            [self registerForTraitChanges:@[UITraitAccessibilityContrast.class] withAction:@selector(setNeedsLayout)];
        } else {
            [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(motionChanged:)
                name:UIAccessibilityDarkerSystemColorsStatusDidChangeNotification object:nil];
        }
    }
    return self;
}
- (void)setText:(NSString *)text {
    if ([self.text isEqualToString:text]) return;
    // Natural paragraph direction follows the first strong character. Ignore
    // prefixes such as dates and punctuation, even when the UI language differs.
    NSString *rightToLeft = @"^[^\\p{bc=L}\\p{bc=R}\\p{bc=AL}]*[\\p{bc=R}\\p{bc=AL}]";
    self.startsAtRight = text.length && [text rangeOfString:rightToLeft options:NSRegularExpressionSearch].location != NSNotFound;
    [super setText:text];
    [self setNeedsLayout];
}
- (void)didMoveToWindow {
    [super didMoveToWindow];
    [NSNotificationCenter.defaultCenter removeObserver:self name:UIAccessibilityReduceMotionStatusDidChangeNotification object:nil];
    if (self.window) {
        [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(motionChanged:)
            name:UIAccessibilityReduceMotionStatusDidChangeNotification object:nil];
    } else {
        [self stopScrolling];
    }
    [self setNeedsLayout];
}
- (void)motionChanged:(NSNotification *)notification {
    [self setNeedsLayout];
}
- (void)stopScrolling {
    if (!self.movingText) return;
    [self.movingText.layer removeAllAnimations];
    [self.movingText removeFromSuperview];
    self.movingText = nil;
    [self setNeedsDisplay];
}
- (void)restartPan {
    [self stopScrolling];
    [self setNeedsLayout];
}
- (void)drawTextInRect:(CGRect)rect {
    if (!self.movingText) [super drawTextInRect:rect];
}
- (void)layoutSubviews {
    [super layoutSubviews];
    CGFloat width = CGRectGetWidth(self.bounds);
    CGFloat textWidth = ceil(self.intrinsicContentSize.width);
    CGFloat travel = textWidth - width;
    if (!self.window || width <= 0 || travel <= 1 || UIAccessibilityIsReduceMotionEnabled() ||
        self.traitCollection.accessibilityContrast == UIAccessibilityContrastHigh) {
        [self stopScrolling];
        return;
    }
    BOOL restart = ![self.movingText.text isEqualToString:self.text] || fabs(self.travel - travel) > 0.5;
    if (!self.movingText) {
        self.clipsToBounds = YES;
        self.movingText = [[UILabel alloc] init];
        self.movingText.isAccessibilityElement = NO;
        [self addSubview:self.movingText];
        [self setNeedsDisplay];
    }
    self.movingText.font = self.font;
    self.movingText.textColor = self.textColor;
    self.movingText.text = self.text;
    self.movingText.frame = CGRectMake(self.startsAtRight ? -travel : 0, 0, textWidth, CGRectGetHeight(self.bounds));
    if (!restart) return;
    self.travel = travel;
    NSTimeInterval pass = MAX(1, travel / 24.0);
    NSTimeInterval pause = 2.0, duration = 2 * (pass + pause);
    CAKeyframeAnimation *pan = [CAKeyframeAnimation animationWithKeyPath:@"transform.translation.x"];
    NSNumber *panOffset = @(self.startsAtRight ? travel : -travel);
    pan.values = @[@0, @0, panOffset, panOffset, @0];
    pan.keyTimes = @[@0, @(pause / duration), @0.5, @((2 * pause + pass) / duration), @1];
    pan.duration = duration;
    [self.movingText.layer addAnimation:pan forKey:@"readTitle"];
}
@end
