#!/bin/bash
# Build script for iOS Memory Leak Detector Xcode Extension

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BUILD_DIR="$SCRIPT_DIR/build"
APP_NAME="MemoryLeakDetector"

echo "=============================================="
echo "  Building iOS Memory Leak Detector Extension"
echo "=============================================="
echo ""

# Check for Xcode
if ! command -v xcodebuild &> /dev/null; then
    echo "Error: Xcode command line tools not installed"
    echo "Run: xcode-select --install"
    exit 1
fi

# Create build directory
mkdir -p "$BUILD_DIR"

# Check if Xcode project exists
if [ ! -d "$SCRIPT_DIR/$APP_NAME/$APP_NAME.xcodeproj" ]; then
    echo "Xcode project not found. Creating project structure..."
    echo ""
    echo "Please follow these steps:"
    echo ""
    echo "1. Open Xcode"
    echo "2. Create new macOS App project:"
    echo "   - Product Name: $APP_NAME"
    echo "   - Bundle ID: com.yoonk.memory-leak-detector"
    echo "   - Language: Swift"
    echo ""
    echo "3. Add Source Editor Extension target:"
    echo "   - File > New > Target > Xcode Source Editor Extension"
    echo "   - Product Name: LeakDetectorExtension"
    echo ""
    echo "4. Copy source files:"
    echo "   cp $SCRIPT_DIR/$APP_NAME/LeakDetectorExtension/*.swift <your-project>/LeakDetectorExtension/"
    echo ""
    echo "5. Build and run the app"
    echo ""
    echo "6. Enable extension in System Settings > Extensions > Xcode Source Editor"
    echo ""
    exit 0
fi

echo "Building extension..."

# Build the project
cd "$SCRIPT_DIR/$APP_NAME"
xcodebuild -scheme "$APP_NAME" -configuration Release -derivedDataPath "$BUILD_DIR/DerivedData" build

# Find the built app
APP_PATH=$(find "$BUILD_DIR/DerivedData" -name "*.app" -type d | head -1)

if [ -z "$APP_PATH" ]; then
    echo "Error: Build failed - app not found"
    exit 1
fi

# Copy to Applications (optional)
echo ""
echo "Build successful!"
echo ""
echo "App location: $APP_PATH"
echo ""
echo "To install:"
echo "1. Run the app once: open \"$APP_PATH\""
echo "2. Enable in System Settings > Extensions > Xcode Source Editor"
echo ""

# Offer to copy to Applications
read -p "Copy to /Applications? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    cp -R "$APP_PATH" /Applications/
    echo "Copied to /Applications/$APP_NAME.app"
fi

echo ""
echo "Done! Restart Xcode to use the extension."
