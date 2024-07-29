import asyncio
import os
import json
import edge_tts
import subprocess
import time
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QProgressBar, QTextEdit, QLabel, QFileDialog, QMessageBox
from PyQt5.QtCore import QThread, pyqtSignal

class AudiobookGenerator(QThread):
    progress_update = pyqtSignal(str)
    progress_value = pyqtSignal(int)

    def __init__(self, input_files, output_folder, ffmpeg_path, ffprobe_path, voice, intro_video, final_video, intro_audio, final_audio, image):
        super().__init__()
        self.input_files = input_files
        self.output_folder = output_folder
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.voice = voice
        self.intro_video = intro_video
        self.final_video = final_video
        self.intro_audio = intro_audio
        self.final_audio = final_audio
        self.image = image

    def format_time(self, seconds):
        return time.strftime("%H:%M:%S", time.gmtime(seconds))

    async def generate_audio(self, input_file):
        self.progress_update.emit(f"Reading text from {input_file}...")
        start_time = time.time()
        with open(input_file, "r", encoding="utf-8") as file:
            text = file.read().strip()

        self.progress_update.emit("Generating audio using edge_tts...")
        communicate = edge_tts.Communicate(text, self.voice)
        audio_output_file = os.path.join(self.output_folder, f"{os.path.splitext(os.path.basename(input_file))[0]}_audio.mp3")
        await communicate.save(audio_output_file)
        end_time = time.time()
        duration = end_time - start_time
        self.progress_update.emit(f"Audio generated in {self.format_time(duration)}.")
        return audio_output_file

    def get_audio_duration(self, audio_file):
        self.progress_update.emit(f"Getting duration of {audio_file}...")
        start_time = time.time()
        cmd = [self.ffprobe_path, "-v", "quiet", "-select_streams", "a:0",
               "-show_entries", "format=duration", "-of", "csv=p=0", audio_file]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        duration = float(output.decode("utf-8"))
        end_time = time.time()
        self.progress_update.emit(f"Duration obtained in {self.format_time(end_time - start_time)}: {self.format_time(duration)}.")
        return duration

    def combine_audio(self, intro_audio, main_audio, final_audio, output_audio):
        self.progress_update.emit(f"Combining audio files...")
        start_time = time.time()
        cmd = [
            self.ffmpeg_path,
            "-i", intro_audio,
            "-i", main_audio,
            "-i", final_audio,
            "-filter_complex", "[0:0][1:0][2:0]concat=n=3:v=0:a=1[out]",
            "-map", "[out]",
            output_audio
        ]
        subprocess.run(cmd)
        end_time = time.time()
        self.progress_update.emit(f"Audio combined in {self.format_time(end_time - start_time)}.")

    def get_duration(self, file):
        cmd = [self.ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout)

    def optimize_video_processing(self, video_initial, image, video_final, main_audio, output_video):
        self.progress_update.emit("Optimizing video processing...")
        start_time = time.time()

        def get_video_info(video_file):
            result = subprocess.run([
                self.ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name,width,height",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_file
            ], capture_output=True, text=True)
            codec, width, height = result.stdout.split()
            return codec, int(width), int(height)

        intro_codec, intro_width, intro_height = get_video_info(video_initial)
        self.progress_update.emit(f"Intro video: codec={intro_codec}, width={intro_width}, height={intro_height}")

        intro_audio_duration = self.get_duration(self.intro_audio)
        main_audio_duration = self.get_duration(main_audio)
        final_audio_duration = self.get_duration(self.final_audio)

        self.progress_update.emit(f"Durations: intro_audio={self.format_time(intro_audio_duration)}, "
                                  f"main_audio={self.format_time(main_audio_duration)}, final_audio={self.format_time(final_audio_duration)}")

        filter_complex = [
            # Video
            f"[0:v]trim=duration={intro_audio_duration},setpts=PTS-STARTPTS[v0]",
            f"[1:v]scale={intro_width}:{intro_height},loop=loop=-1:size=1:start=0,setpts=PTS-STARTPTS,trim=duration={main_audio_duration}[v1]",
            f"[2:v]trim=duration={final_audio_duration},setpts=PTS-STARTPTS[v2]",
            f"[v0][v1][v2]concat=n=3:v=1:a=0[outv]",
            # Audio
            f"[3:a]asetpts=PTS-STARTPTS[a0]",
            f"[4:a]asetpts=PTS-STARTPTS[a1]",
            f"[5:a]asetpts=PTS-STARTPTS[a2]",
            f"[a0][a1][a2]concat=n=3:v=0:a=1[outa]"
        ]

        cmd = [
            self.ffmpeg_path,
            "-i", video_initial,
            "-loop", "1", "-i", image,
            "-i", video_final,
            "-i", self.intro_audio,
            "-i", main_audio,
            "-i", self.final_audio,
            "-filter_complex", ";".join(filter_complex),
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            output_video
        ]

        self.progress_update.emit("Executing ffmpeg command...")
        subprocess.run(cmd, check=True)

        end_time = time.time()
        self.progress_update.emit(f"Video processing completed in {self.format_time(end_time - start_time)}.")

    async def process_file(self, input_file):
        try:
            self.progress_update.emit(f"Processing {os.path.basename(input_file)}...")
            
            audio_start_time = time.time()
            audio_file = await self.generate_audio(input_file)
            audio_end_time = time.time()
            self.progress_update.emit(f"Audio generation for {input_file} took {self.format_time(audio_end_time - audio_start_time)}.")

            video_start_time = time.time()
            output_video = os.path.join(self.output_folder, f"{os.path.splitext(os.path.basename(input_file))[0]}.mp4")
            self.optimize_video_processing(self.intro_video, self.image, self.final_video, audio_file, output_video)
            video_end_time = time.time()
            self.progress_update.emit(f"Video generation took {self.format_time(video_end_time - video_start_time)}.")

            os.remove(audio_file)

            self.progress_update.emit(f"Video created: {output_video}")

        except Exception as e:
            self.progress_update.emit(f"An error occurred while processing {input_file}: {str(e)}")

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        total_files = len(self.input_files)
        overall_start_time = time.time()
        for i, file in enumerate(self.input_files, 1):
            loop.run_until_complete(self.process_file(file))
            self.progress_value.emit(int((i / total_files) * 100))
        
        overall_end_time = time.time()
        self.progress_update.emit(f"All files processed in {self.format_time(overall_end_time - overall_start_time)}.")
        loop.close()

class ImprovedUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.generator = None
        self.settings_file = "audiobook_generator_settings.json"
        self.load_settings()

    def initUI(self):
        self.setWindowTitle('Audiobook Generator')
        self.setGeometry(100, 100, 800, 600)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        main_layout = QHBoxLayout()
        main_widget.setLayout(main_layout)

        left_panel = QVBoxLayout()
        self.file_list = QListWidget()
        left_panel.addWidget(QLabel('Files to Process:'))
        left_panel.addWidget(self.file_list)

        file_controls = QHBoxLayout()
        self.add_file_btn = QPushButton('Add File(s)')
        self.add_folder_btn = QPushButton('Add Folder')
        self.remove_file_btn = QPushButton('Remove File')
        file_controls.addWidget(self.add_file_btn)
        file_controls.addWidget(self.add_folder_btn)
        file_controls.addWidget(self.remove_file_btn)
        left_panel.addLayout(file_controls)

        self.select_image_btn = QPushButton('Select Custom Image')
        left_panel.addWidget(self.select_image_btn)

        self.process_btn = QPushButton('Process Files')
        left_panel.addWidget(self.process_btn)

        main_layout.addLayout(left_panel)

        right_panel = QVBoxLayout()
        self.progress_bar = QProgressBar()
        right_panel.addWidget(QLabel('Overall Progress:'))
        right_panel.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        right_panel.addWidget(QLabel('Processing Log:'))
        right_panel.addWidget(self.log_text)

        main_layout.addLayout(right_panel)

        self.add_file_btn.clicked.connect(self.add_files)
        self.add_folder_btn.clicked.connect(self.add_folder)
        self.remove_file_btn.clicked.connect(self.remove_file)
        self.select_image_btn.clicked.connect(self.select_image)
        self.process_btn.clicked.connect(self.process_files)

        self.custom_image = None
        self.ffmpeg_path = None
        self.ffprobe_path = None
        self.intro_video = None
        self.final_video = None
        self.intro_audio = None
        self.final_audio = None
        self.output_folder = None
        self.voice = "pt-BR-AntonioNeural"

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Text Files", "", "Text Files (*.txt)")
        for file in files:
            self.file_list.addItem(file)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            for file in os.listdir(folder):
                if file.endswith('.txt'):
                    self.file_list.addItem(os.path.join(folder, file))

    def remove_file(self):
        current_item = self.file_list.currentItem()
        if current_item:
            self.file_list.takeItem(self.file_list.row(current_item))

    def select_image(self):
        self.custom_image, _ = QFileDialog.getOpenFileName(self, "Select Custom Image", "", "Image Files (*.png *.jpg *.jpeg)")
        if self.custom_image:
            self.log_text.append(f"Custom image selected: {self.custom_image}")

    def setup_paths(self):
        if not self.load_settings():
            self.ffmpeg_path, _ = QFileDialog.getOpenFileName(self, "Select FFmpeg executable", "", "Executable files (*.exe)")
            self.ffprobe_path, _ = QFileDialog.getOpenFileName(self, "Select FFprobe executable", "", "Executable files (*.exe)")
            self.intro_video, _ = QFileDialog.getOpenFileName(self, "Select Intro Video", "", "Video Files (*.mp4)")
            self.final_video, _ = QFileDialog.getOpenFileName(self, "Select Final Video", "", "Video Files (*.mp4)")
            self.intro_audio, _ = QFileDialog.getOpenFileName(self, "Select Intro Audio", "", "Audio Files (*.mp3)")
            self.final_audio, _ = QFileDialog.getOpenFileName(self, "Select Final Audio", "", "Audio Files (*.mp3)")
            self.output_folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
            self.save_settings()

    def save_settings(self):
        settings = {
            "ffmpeg_path": self.ffmpeg_path,
            "ffprobe_path": self.ffprobe_path,
            "intro_video": self.intro_video,
            "final_video": self.final_video,
            "intro_audio": self.intro_audio,
            "final_audio": self.final_audio,
            "output_folder": self.output_folder
        }
        with open(self.settings_file, "w") as f:
            json.dump(settings, f)

    def load_settings(self):
        if os.path.exists(self.settings_file):
            with open(self.settings_file, "r") as f:
                settings = json.load(f)
            self.ffmpeg_path = settings.get("ffmpeg_path")
            self.ffprobe_path = settings.get("ffprobe_path")
            self.intro_video = settings.get("intro_video")
            self.final_video = settings.get("final_video")
            self.intro_audio = settings.get("intro_audio")
            self.final_audio = settings.get("final_audio")
            self.output_folder = settings.get("output_folder")
            return True
        return False

    def process_files(self):
        if self.file_list.count() == 0:
            QMessageBox.warning(self, "No Files", "Please add files to process.")
            return

        if not all([self.ffmpeg_path, self.ffprobe_path, self.intro_video, self.final_video, self.intro_audio, self.final_audio, self.output_folder]):
            self.setup_paths()

        if not all([self.ffmpeg_path, self.ffprobe_path, self.intro_video, self.final_video, self.intro_audio, self.final_audio, self.output_folder]):
            return

        input_files = [self.file_list.item(i).text() for i in range(self.file_list.count())]
        image = self.custom_image if self.custom_image else "video/Thumb.png"

        self.generator = AudiobookGenerator(
            input_files, self.output_folder, self.ffmpeg_path, self.ffprobe_path,
            self.voice, self.intro_video, self.final_video, self.intro_audio, self.final_audio, image
        )
        self.generator.progress_update.connect(self.update_log)
        self.generator.progress_value.connect(self.update_progress)
        self.generator.start()

    def update_log(self, message):
        self.log_text.append(message)

    def update_progress(self, value):
        self.progress_bar.setValue(value)

if __name__ == '__main__':
    app = QApplication([])
    ex = ImprovedUI()
    ex.show()
    app.exec_()
