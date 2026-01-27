#pragma once
#include <QScreen>
#include <QWidget>

class OverlayWindow : public QWidget {
  Q_OBJECT
public:
  explicit OverlayWindow(QScreen *screen, QWidget *parent = nullptr);
  void setOpacity(double level);

protected:
  void paintEvent(QPaintEvent * /*event*/) override;

private:
  double m_opacity = 0.0;
  static constexpr double MAX_OPACITY = 0.85;
};
