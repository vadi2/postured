#include "overlaywindow.h"
#include <LayerShellQt/Window>
#include <QPainter>

OverlayWindow::OverlayWindow(QScreen *screen, QWidget *parent)
    : QWidget(parent, Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint) {
  setAttribute(Qt::WA_TranslucentBackground);
  setAttribute(Qt::WA_ShowWithoutActivating);

  // Must create window handle before configuring layer-shell
  setScreen(screen);
  setGeometry(screen->geometry());
  create();

  // Configure layer-shell
  if (auto *lsWindow = LayerShellQt::Window::get(windowHandle())) {
    lsWindow->setLayer(LayerShellQt::Window::LayerOverlay);
    lsWindow->setAnchors(LayerShellQt::Window::Anchors(
        LayerShellQt::Window::AnchorTop | LayerShellQt::Window::AnchorBottom |
        LayerShellQt::Window::AnchorLeft | LayerShellQt::Window::AnchorRight));
    lsWindow->setExclusiveZone(-1);
    lsWindow->setKeyboardInteractivity(
        LayerShellQt::Window::KeyboardInteractivityNone);
  }

  show();
}

void OverlayWindow::setOpacity(double level) {
  m_opacity = qBound(0.0, level, 1.0);
  update();
}

void OverlayWindow::paintEvent(QPaintEvent *) {
  QPainter painter(this);
  painter.fillRect(rect(), QColor(0, 0, 0, int(m_opacity * MAX_OPACITY * 255)));
}
