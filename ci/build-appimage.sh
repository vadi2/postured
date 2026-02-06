#!/bin/bash
# Build script for Postured AppImage using TheAssassin's linuxdeploy ecosystem
# Requirements: bash, wget, fuse (for running AppImages)

set -e

APP_NAME="postured"
APP_VERSION="1.4.1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${SCRIPT_DIR}/appimage-build"
APPDIR="${BUILD_DIR}/${APP_NAME}.AppDir"
TOOLS_DIR="${BUILD_DIR}/tools"

echo "=== Building ${APP_NAME} AppImage v${APP_VERSION} ==="

# Clean previous build
rm -rf "${BUILD_DIR}"
mkdir -p "${APPDIR}" "${TOOLS_DIR}"

# Download fresh linuxdeploy tools (ensures latest patchelf for page alignment fixes)
echo "=== Downloading linuxdeploy tools ==="
cd "${TOOLS_DIR}"

rm -f linuxdeploy-x86_64.AppImage
wget -nv "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage"
chmod +x linuxdeploy-x86_64.AppImage

rm -f linuxdeploy-plugin-conda.sh
wget -nv "https://raw.githubusercontent.com/linuxdeploy/linuxdeploy-plugin-conda/master/linuxdeploy-plugin-conda.sh"
chmod +x linuxdeploy-plugin-conda.sh

rm -f linuxdeploy-plugin-appimage-x86_64.AppImage
wget -nv "https://github.com/linuxdeploy/linuxdeploy-plugin-appimage/releases/download/continuous/linuxdeploy-plugin-appimage-x86_64.AppImage"
chmod +x linuxdeploy-plugin-appimage-x86_64.AppImage

# appimagelint (by TheAssassin) - for validation
if [ ! -f appimagelint-x86_64.AppImage ]; then
    wget -nv "https://github.com/TheAssassin/appimagelint/releases/download/continuous/appimagelint-x86_64.AppImage" || echo "Warning: appimagelint not available, skipping validation"
fi

cd "${SCRIPT_DIR}"

# Set up conda plugin environment variables
export CONDA_PLUGINS_AUTO_ACCEPT_TOS=yes
export CONDA_CHANNELS="conda-forge"
# Use conda-forge for numpy/opencv (proper page alignment for 16k/64k page size systems)
export CONDA_PACKAGES="python=3.11;pyqt>=6.6;numpy;opencv"
export PIP_REQUIREMENTS="mediapipe>=0.10.0 ."
export PIP_WORKDIR="${PROJECT_DIR}"
export CONDA_DOWNLOAD_DIR="${TOOLS_DIR}/conda-cache"
mkdir -p "${CONDA_DOWNLOAD_DIR}"

# Prepare desktop file and icon
echo "=== Setting up AppDir structure ==="
mkdir -p "${APPDIR}/usr/share/applications"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/scalable/apps"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/256x256/apps"

cp "${PROJECT_DIR}/postured/resources/postured.desktop" "${APPDIR}/usr/share/applications/"
cp "${PROJECT_DIR}/postured/resources/icons/postured.svg" "${APPDIR}/usr/share/icons/hicolor/scalable/apps/io.github.vadi2.postured.svg"

# Convert SVG to PNG for compatibility (if rsvg-convert is available)
if command -v rsvg-convert &> /dev/null; then
    rsvg-convert -w 256 -h 256 "${PROJECT_DIR}/postured/resources/icons/postured.svg" \
        -o "${APPDIR}/usr/share/icons/hicolor/256x256/apps/io.github.vadi2.postured.png"
fi

# Root level links (required by AppImage spec)
cp "${PROJECT_DIR}/postured/resources/postured.desktop" "${APPDIR}/"
cp "${PROJECT_DIR}/postured/resources/icons/postured.svg" "${APPDIR}/io.github.vadi2.postured.svg"

# Create the AppRun script OUTSIDE the AppDir (linuxdeploy will copy it in)
# Note: --custom-apprun source must not be inside the AppDir, or linuxdeploy
# will delete the file before trying to copy it, causing a failure.
echo "=== Creating AppRun script ==="
APPRUN_FILE="${BUILD_DIR}/AppRun"
cat > "${APPRUN_FILE}" << 'APPRUN_EOF'
#!/bin/bash
# AppRun for Postured
SELF=$(readlink -f "$0")
HERE=${SELF%/*}

# Set up conda environment
export PATH="${HERE}/usr/conda/bin:${PATH}"
export PYTHONHOME="${HERE}/usr/conda"
export PYTHONPATH="${HERE}/usr/conda/lib/python3.11/site-packages"

# Qt/PyQt6 environment
export QT_PLUGIN_PATH="${HERE}/usr/conda/lib/qt6/plugins"
export QML2_IMPORT_PATH="${HERE}/usr/conda/lib/qt6/qml"

# Prevent loading system Python modules
export PYTHONDONTWRITEBYTECODE=1

# Library paths
export LD_LIBRARY_PATH="${HERE}/usr/conda/lib:${HERE}/usr/lib:${LD_LIBRARY_PATH}"

# XDG paths for proper desktop integration
export XDG_DATA_DIRS="${HERE}/usr/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"

# X11/XKB keyboard configuration (required by Qt/Wayland)
# Override compiled-in paths from CI environment
export XKB_CONFIG_ROOT="${HERE}/usr/conda/share/X11/xkb"

# Fontconfig - use bundled config
export FONTCONFIG_PATH="${HERE}/usr/conda/etc/fonts"
export FONTCONFIG_FILE="${HERE}/usr/conda/etc/fonts/fonts.conf"

# Run the application
exec "${HERE}/usr/conda/bin/python" -m postured "$@"
APPRUN_EOF
chmod +x "${APPRUN_FILE}"

# Run linuxdeploy with conda plugin to set up Python environment
echo "=== Running linuxdeploy with conda plugin ==="
cd "${BUILD_DIR}"

"${TOOLS_DIR}/linuxdeploy-x86_64.AppImage" \
    --appdir "${APPDIR}" \
    --plugin conda \
    --custom-apprun "${APPRUN_FILE}" \
    --desktop-file "${PROJECT_DIR}/postured/resources/postured.desktop" \
    --icon-file "${APPDIR}/usr/share/icons/hicolor/scalable/apps/io.github.vadi2.postured.svg"

# Remove unnecessary files to reduce AppImage size
# The conda environment includes many dependencies we don't need at runtime
echo "=== Trimming AppDir to reduce size ==="

CONDA_DIR="${APPDIR}/usr/conda"
SIZE_BEFORE=$(du -sm "${APPDIR}" | cut -f1)

# Tesseract OCR training data - pulled in by opencv, not used by postured
rm -rf "${CONDA_DIR}/share/tessdata"

# Development headers - not needed at runtime
rm -rf "${CONDA_DIR}/include"

# NOTE: We cannot remove opencv_contrib_python.libs/opencv_python.libs because
# mediapipe depends on pip's opencv-python which needs its bundled libraries.
# This duplicates some libs with conda's opencv but is required for runtime.

# LLVM - pulled in by Mesa for software rendering, not needed
rm -f "${CONDA_DIR}/lib/libLLVM"*.so*

# NOTE: Cannot remove Qt5 libraries - pip's opencv-python is built with Qt5 GUI support

# Build tools not needed at runtime
rm -rf "${CONDA_DIR}/lib/python3.11/site-packages/sipbuild"

# Database clients not used by postured
rm -rf "${CONDA_DIR}/share/mysql"
rm -f "${CONDA_DIR}/lib/libmysqlclient"*.so*

# GObject introspection files - not needed at runtime
rm -rf "${CONDA_DIR}/share/gir-1.0"

# Static libraries (if any remain)
find "${CONDA_DIR}" -name "*.a" -delete 2>/dev/null || true

# Python bytecode cache (regenerated at runtime)
find "${CONDA_DIR}" -name "*.pyc" -delete 2>/dev/null || true
find "${CONDA_DIR}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Strip debug symbols from binaries to reduce size
echo "=== Stripping binaries ==="
find "${APPDIR}" -type f -executable -exec strip --strip-unneeded {} \; 2>/dev/null || true
find "${APPDIR}" -name "*.so*" -exec strip --strip-unneeded {} \; 2>/dev/null || true

SIZE_AFTER=$(du -sm "${APPDIR}" | cut -f1)
echo "=== Trimming complete: ${SIZE_BEFORE}MB -> ${SIZE_AFTER}MB ==="

# Create the final AppImage
echo "=== Creating AppImage ==="
export VERSION="${APP_VERSION}"
export OUTPUT="${PROJECT_DIR}/${APP_NAME}-${APP_VERSION}-x86_64.AppImage"

"${TOOLS_DIR}/linuxdeploy-x86_64.AppImage" \
    --appdir "${APPDIR}" \
    --output appimage

# Validate with appimagelint if available
if [ -f "${TOOLS_DIR}/appimagelint-x86_64.AppImage" ]; then
    echo "=== Validating with appimagelint ==="
    "${TOOLS_DIR}/appimagelint-x86_64.AppImage" "${OUTPUT}" || echo "Warning: Some appimagelint checks failed"
fi

echo ""
echo "=== Build complete! ==="
echo "AppImage created: ${OUTPUT}"
echo ""
echo "To test: ./${APP_NAME}-${APP_VERSION}-x86_64.AppImage"
