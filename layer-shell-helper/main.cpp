#include "overlaywindow.h"
#include <QApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QScreen>
#include <QSocketNotifier>
#include <QTextStream>
#include <unistd.h>

int main(int argc, char *argv[]) {
  QApplication app(argc, argv);

  QVector<OverlayWindow *> windows;
  QStringList monitorNames;

  // Create overlay for each screen
  for (QScreen *screen : QGuiApplication::screens()) {
    auto *window = new OverlayWindow(screen);
    windows.append(window);
    monitorNames.append(screen->name());
  }

  // Send ready message
  QJsonObject ready;
  ready["status"] = "ready";
  ready["monitors"] = QJsonArray::fromStringList(monitorNames);
  QTextStream out(stdout);
  out << QJsonDocument(ready).toJson(QJsonDocument::Compact) << "\n";
  out.flush();

  // Listen for commands on stdin
  auto *notifier =
      new QSocketNotifier(STDIN_FILENO, QSocketNotifier::Read, &app);
  QObject::connect(notifier, &QSocketNotifier::activated, [&]() {
    QTextStream in(stdin);
    QString line = in.readLine();
    if (line.isEmpty())
      return;

    QJsonObject cmd = QJsonDocument::fromJson(line.toUtf8()).object();
    QString action = cmd["cmd"].toString();

    if (action == "set_opacity") {
      double value = cmd["value"].toDouble();
      for (auto *w : windows)
        w->setOpacity(value);
    } else if (action == "quit") {
      QApplication::quit();
    }
  });

  return app.exec();
}
