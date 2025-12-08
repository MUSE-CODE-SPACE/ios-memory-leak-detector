# iOS Memory Leak Detector - Xcode Extension

Xcode Source Editor Extension for detecting and fixing memory leaks directly in your code.

## Features

- **Analyze for Memory Leaks**: Adds warning comments above potential issues
- **Quick Fix Memory Leaks**: Automatically fixes common issues like:
  - Missing `[weak self]` in closures
  - Non-weak delegates
  - Strong IBOutlets
  - Missing `__weak` in Objective-C blocks

## Installation

### Option 1: Build from Source (Recommended)

1. **Open Xcode and create a new project:**
   - File > New > Project
   - macOS > App
   - Product Name: `MemoryLeakDetector`
   - Bundle Identifier: `com.yoonk.memory-leak-detector`
   - Language: Swift

2. **Add Source Editor Extension target:**
   - File > New > Target
   - macOS > Xcode Source Editor Extension
   - Product Name: `LeakDetectorExtension`

3. **Copy the source files:**
   ```bash
   # Copy extension files
   cp LeakDetectorExtension/*.swift /path/to/your/project/LeakDetectorExtension/
   cp LeakDetectorExtension/Info.plist /path/to/your/project/LeakDetectorExtension/
   ```

4. **Build and run:**
   - Select the main app scheme
   - Build (Cmd+B)
   - Run (Cmd+R) - this will launch a secondary Xcode instance

5. **Enable the extension:**
   - System Settings > Privacy & Security > Extensions > Xcode Source Editor
   - Enable "Memory Leak Detector"

### Option 2: Use the Build Script

```bash
./build_extension.sh
```

This creates a signed app bundle ready for installation.

## Usage

1. Open any Swift or Objective-C file in Xcode
2. Select code or place cursor in the file
3. Go to **Editor** menu
4. Choose one of:
   - **Analyze for Memory Leaks** - Shows warnings
   - **Quick Fix Memory Leaks** - Auto-fixes issues

### Keyboard Shortcuts

You can add custom shortcuts:
1. Xcode > Settings > Key Bindings
2. Search for "Memory Leak"
3. Add your preferred shortcuts

## What Gets Detected

### Swift
- Closures capturing `self` without `[weak self]`
- Non-weak delegate properties
- Strong IBOutlets
- Timer closures without weak self
- DispatchQueue closures with self
- Sync on main queue (deadlock risk)

### Objective-C
- Blocks using `self` without `__weak`
- Strong delegate properties
- Strong IBOutlets
- NSTimer retain issues

## Troubleshooting

### Extension not appearing
1. Quit Xcode completely
2. Go to System Settings > Privacy & Security > Extensions > Xcode Source Editor
3. Make sure the extension is enabled
4. Restart Xcode

### Extension crashes
- Check Console.app for crash logs
- Try rebuilding with debugging enabled

### Code signing issues
```bash
codesign --force --deep --sign - MemoryLeakDetector.app
```

## Development

To debug the extension:
1. Set the extension as the active scheme
2. Run with debugging (Cmd+R)
3. In the launched Xcode instance, open a file and trigger the extension
4. Breakpoints in your code will be hit

## License

MIT License - See main project LICENSE file.
