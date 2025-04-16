import sys
import os
import json
import requests
import vlc
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QListWidget, QLabel, QSlider, QSystemTrayIcon, QMenu, QStyle, QMainWindow
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QIcon
from bs4 import BeautifulSoup


HISTORY_FILE = "search_history.json"


class HitmoParser:
    main_link = "https://rus.hitmotop.com/"

    def __init__(self):
        self.track_list = []

    def find_song(self, song_name: str) -> str:
        return self.main_link + "search?q=" + "+".join(song_name.strip().split())

    def get_songs(self, link) -> list:
        self.track_list = []
        try:
            r = requests.get(link, timeout=5)
        except Exception as e:
            print(f"⚠ Ошибка запроса: {e}")
            return []

        bs = BeautifulSoup(r.text, features="html.parser")
        tracks = bs.find_all("li", {"class": "tracks__item"})

        for track in tracks:
            try:
                title = track.find("div", {"class": "track__title"}).text.strip()
                artist = track.find("div", {"class": "track__desc"}).text.strip()
                download = track.find("a", {"class": "track__download-btn"})["href"]
                cover = track.find("div", {"class": "track__img"}).get("style")
                cover_url = None
                if cover and "url(" in cover:
                    start = cover.find("url(") + 4
                    end = cover.find(")", start)
                    cover_url = cover[start:end].strip('"').strip("'")

                self.track_list.append({
                    "title": title,
                    "artist": artist,
                    "download": download,
                    "cover": cover_url
                })
            except Exception as e:
                print(f"⚠ Ошибка обработки трека: {e}")
        return self.track_list


class MusicClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hitmotop Client")
        self.setGeometry(200, 200, 600, 500)

        self.widget = QWidget()
        self.setCentralWidget(self.widget)
        self.layout = QVBoxLayout(self.widget)

        # Поисковая строка и кнопка
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Введите название трека")
        self.search_btn = QPushButton("🔍 Поиск")
        self.search_btn.clicked.connect(self.search_tracks)

        search_layout = QHBoxLayout()
        search_layout.addWidget(self.search_box)
        search_layout.addWidget(self.search_btn)
        self.layout.addLayout(search_layout)

        # История поиска
        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self.search_from_history)
        self.layout.addWidget(self.history_list)
        self.load_history()

        # Список треков
        self.results_list = QListWidget()
        self.results_list.itemClicked.connect(self.play_selected_track)
        self.layout.addWidget(self.results_list)

        # Обложка
        self.cover_label = QLabel()
        self.cover_label.setFixedHeight(150)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.cover_label)

        # Время
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.time_label)

        # Слайдер воспроизведения
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderReleased.connect(self.set_track_position)
        self.layout.addWidget(self.slider)

        # Кнопки управления
        controls = QHBoxLayout()
        self.play_btn = QPushButton("▶️ Играть")
        self.play_btn.clicked.connect(self.toggle_play)
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(70)
        self.vol_slider.valueChanged.connect(self.set_volume)
        controls.addWidget(self.play_btn)
        controls.addWidget(QLabel("🔊"))
        controls.addWidget(self.vol_slider)
        self.layout.addLayout(controls)

        # Системный трей
        self.tray = QSystemTrayIcon(QIcon.fromTheme("media-playback-start"), self)
        self.tray.setToolTip("Hitmotop Client")
        self.tray_menu = QMenu()
        self.tray_menu.addAction("Показать", self.show)
        self.tray_menu.addAction("Выход", QApplication.quit)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.setVisible(True)

        # Плеер и таймер
        self.player = vlc.MediaPlayer()
        self.player.audio_set_volume(70)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)

        # Данные
        self.track_links = []
        self.cover_urls = []
        self.current_index = -1

    def show_notification(self, text):
        self.tray.showMessage("🎵 Сейчас играет:", text)

    def save_history(self):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump([self.history_list.item(i).text() for i in range(self.history_list.count())], f)

    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
                for item in history:
                    self.history_list.addItem(item)

    def add_to_history(self, query):
        for i in range(self.history_list.count()):
            if self.history_list.item(i).text().lower() == query.lower():
                self.history_list.takeItem(i)
                break
        self.history_list.insertItem(0, query)
        while self.history_list.count() > 10:
            self.history_list.takeItem(10)
        self.save_history()

    def search_from_history(self, item):
        self.search_box.setText(item.text())
        self.search_tracks()

    def search_tracks(self):
        query = self.search_box.text().strip()
        if not query:
            return

        self.add_to_history(query)
        self.results_list.clear()
        self.track_links.clear()
        self.cover_urls.clear()
        self.cover_label.clear()

        parser = HitmoParser()
        url = parser.find_song(query)
        print(f"🔎 Открываю: {url}")
        tracks = parser.get_songs(url)

        if not tracks:
            self.results_list.addItem("⚠ Треки не найдены.")
            return

        for t in tracks:
            name = f"{t['artist']} — {t['title']}"
            self.results_list.addItem(name)
            self.track_links.append(t["download"])
            self.cover_urls.append(t["cover"])

    def play_selected_track(self, item):
        index = self.results_list.currentRow()
        if index < 0 or index >= len(self.track_links):
            return

        link = self.track_links[index]
        self.current_index = index

        media = vlc.Media(link)
        self.player.set_media(media)
        self.player.play()
        self.play_btn.setText("⏸ Пауза")
        self.timer.start(1000)

        self.show_notification(self.results_list.item(index).text())

        cover_url = self.cover_urls[index]
        if cover_url:
            try:
                response = requests.get(cover_url, timeout=5)
                pixmap = QPixmap()
                pixmap.loadFromData(response.content)
                self.cover_label.setPixmap(pixmap.scaledToHeight(150))
            except Exception as e:
                print(f"⚠ Ошибка загрузки обложки: {e}")

    def toggle_play(self):
        if self.player.is_playing():
            self.player.pause()
            self.play_btn.setText("▶️ Играть")
        else:
            self.player.play()
            self.play_btn.setText("⏸ Пауза")

    def update_ui(self):
        try:
            length = self.player.get_length()
            current = self.player.get_time()
            if length > 0:
                self.slider.setValue(int(current / length * 1000))
                self.time_label.setText(
                    f"{self.ms_to_min(current)} / {self.ms_to_min(length)}"
                )
        except:
            pass

    def set_track_position(self):
        try:
            pos = self.slider.value()
            length = self.player.get_length()
            if length > 0:
                self.player.set_time(int(length * pos / 1000))
        except:
            pass

    def set_volume(self, val):
        self.player.audio_set_volume(val)

    def ms_to_min(self, ms):
        s = int(ms / 1000)
        return f"{s // 60:02}:{s % 60:02}"


if __name__ == '__main__':
    app = QApplication(sys.argv)
    client = MusicClient()
    client.show()
    sys.exit(app.exec())
