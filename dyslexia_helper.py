import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, font
import threading
import json
import re

from capture_client import CaptureTranscriptionClient


class DyslexiaFrontendApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Okuma Arkadaşım")
        self.root.geometry("800x600")

        self.load_config()
        self.setup_styles()

        self.reference_words = []
        self.next_word_index = 0

        self.sample_texts = {
            "Kısa Metin (Kolay)": "Küçük kedi bahçede oyun oynuyor. Renkli bir kelebek gördü ve peşinden koştu.",
            "Orta Metin": "Ali okula giderken yolda arkadaşı Ayşe'yi gördü. Birlikte yürümeye başladılar. Hava çok güzeldi ve kuşlar ötüyordu.",
            "Uzun Metin (Zor)": "Geçen hafta sonu ailemle birlikte pikniğe gittik. Yeşil çimenlerin üzerine battaniyemizi serdik. Annem lezzetli sandviçler hazırlamıştı. Kardeşim top oynamak istedi ve hep beraber oynadık."
        }

        self.create_notebook()

        self.transcription_client = None
        self.is_streaming = False

        self.all_segments = []

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                self.config = json.load(f)
        except:
            self.config = {
                "host": "localhost",
                "port": 9090,
                "model": "large-v3-turbo",
                "lang": "tr",
                "use_vad": False
            }
            self.save_config()

    def save_config(self):
        with open('config.json', 'w') as f:
            json.dump(self.config, f)

    def create_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill='both', padx=10, pady=5)

        self.create_main_frame()
        self.create_results_frame()

    def create_main_frame(self):
        main_frame = ttk.Frame(self.notebook)
        self.notebook.add(main_frame, text='Okuma Sayfası')

        text_frame = ttk.LabelFrame(main_frame, text='Metin Seçimi', padding=10)
        text_frame.pack(fill='x', padx=10, pady=5)

        self.radio_buttons = []
        self.text_var = tk.StringVar()
        for text_name in self.sample_texts.keys():
            rb = ttk.Radiobutton(
                text_frame,
                text=text_name,
                variable=self.text_var,
                value=text_name,
                command=self.update_text
            )
            rb.pack(anchor='w')
            self.radio_buttons.append(rb)

        self.custom_button = ttk.Button(
            text_frame,
            text='Kendi Metnimi Girmek İstiyorum',
            command=self.toggle_custom_text,
            style='Kid.TButton'
        )
        self.custom_button.pack(pady=5)

        self.reading_frame = ttk.LabelFrame(main_frame, text='Okuma Metni', padding=10)
        self.reading_frame.pack(fill='both', expand=True, padx=10, pady=5)

        self.text_area = scrolledtext.ScrolledText(
            self.reading_frame, wrap=tk.WORD,
            font=('Comic Sans MS', 14), height=8
        )
        self.text_area.pack(fill='both', expand=True)

        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill='x', padx=10, pady=5)

        ttk.Button(control_frame, text='⚙️ Ayarlar', command=self.show_settings).pack(side='left', padx=5)

        self.record_button = ttk.Button(
            control_frame, text='🎤 Okumaya Başla',
            command=self.toggle_streaming,
            style='Kid.TButton'
        )
        self.record_button.pack(side='right', padx=5)

        self.text_area.tag_config('high_conf', foreground='green')
        self.text_area.tag_config('med_conf', foreground='orange')
        self.text_area.tag_config('low_conf', foreground='red')

    def create_results_frame(self):
        results_frame = ttk.Frame(self.notebook)
        self.notebook.add(results_frame, text='Sonuçlar')

        self.results_text = scrolledtext.ScrolledText(
            results_frame,
            wrap=tk.WORD,
            font=('Comic Sans MS', 12),
            height=20,
            background='#FFFAF0'
        )
        underline_font = font.Font(family='Comic Sans MS', size=12, underline=True)
        self.results_text.pack(fill='both', expand=True, padx=10, pady=5)

        self.results_text.tag_configure('green', foreground='#2E8B57')
        self.results_text.tag_configure('yellow', foreground='#DAA520')
        self.results_text.tag_configure('red', foreground='#CD5C5C')
        self.results_text.tag_configure('blue', foreground='#4682B4')
        self.results_text.tag_configure('purple', foreground='#9370DB')
        self.results_text.tag_configure('blue_bold', font=underline_font, foreground='blue')

    def remove_punctuation_and_lowercase(self, text):
        text_no_punc = re.sub(r'[^\w\s]', '', text)
        return text_no_punc.lower()

    def detect_stuttering(self):
        stuttering = []

        for segment in self.all_segments:
            clean_text = re.sub(r'[^\w\s]', ' ', segment['text'])
            words = clean_text.lower().split()

            for i, word in enumerate(words):
                if not word:
                    continue

                if i > 0 and word == words[i - 1]:
                    stuttering.append({
                        'type': 'tekrar',
                        'word': word,
                        'timestamp': round(float(segment['start']), 2)
                    })

                if '-' in word:
                    parts = word.split('-')
                    if len(parts) >= 2 and any(p and parts[-1].startswith(p) for p in parts[:-1]):
                        stuttering.append({
                            'type': 'kekeme',
                            'word': word,
                            'timestamp': round(float(segment['start']), 2)
                        })

                vowels = 'aeıioöuü'
                for v in vowels:
                    if v * 3 in word:
                        stuttering.append({
                            'type': 'uzatma',
                            'word': word,
                            'timestamp': round(float(segment['start']), 2)
                        })
                        break

        return stuttering

    def analyze_reading(self):
        analysis = {
            'hesitations': [],
            'pauses': [],
            'mispronunciations': [],
            'reading_speed': 0.0,
            'accuracy': 0.0
        }

        spoken_text_raw = " ".join([s['text'] for s in self.all_segments])
        spoken_cleaned = self.remove_punctuation_and_lowercase(spoken_text_raw)
        spoken_words = spoken_cleaned.split()

        ref_words = [self.remove_punctuation_and_lowercase(w) for w in self.reference_words]

        if not spoken_words:
            return analysis

        total_time = float(self.all_segments[-1]['end']) - float(self.all_segments[0]['start'])
        if total_time > 0:
            analysis['reading_speed'] = len(spoken_words) / (total_time / 60)
        else:
            analysis['reading_speed'] = 0

        for i in range(len(self.all_segments) - 1):
            pause_duration = float(self.all_segments[i + 1]['start']) - float(self.all_segments[i]['end'])
            if pause_duration > 1.0:
                analysis['pauses'].append({
                    'duration': round(pause_duration, 2),
                    'position': self.all_segments[i]['text']
                })

        analysis['hesitations'] = self.detect_stuttering()

        for spoken_word in spoken_words:
            if spoken_word not in ref_words:
                analysis['mispronunciations'].append(spoken_word)

        if ref_words:
            matched_words = set()
            correct_words = 0
            for w in spoken_words:
                if w in ref_words and w not in matched_words:
                    correct_words += 1
                    matched_words.add(w)
            analysis['accuracy'] = (correct_words / len(ref_words)) * 100

        return analysis

    def format_analysis_results(self, analysis):
        self.results_text.delete(1.0, tk.END)

        self.results_text.insert(tk.END, "🌈 OKUMA RAPORUM 🌈\n\n", 'purple')
        self.results_text.insert(tk.END, "🎯 Nasıl Okudum?\n", 'underline_font')

        accuracy = analysis['accuracy']
        speed = analysis['reading_speed']

        if accuracy >= 90:
            self.results_text.insert(tk.END, f"🟢 Doğruluk: %{accuracy:.1f} - Harika okudun! Çok başarılısın! 🏆\n",
                                     'green')
        elif accuracy >= 70:
            self.results_text.insert(tk.END,
                                     f"🟡 Doğruluk: %{accuracy:.1f} - İyi iş çıkardın! Biraz daha pratik yapalım! 👍\n",
                                     'yellow')
        else:
            self.results_text.insert(tk.END, f"🔴 Doğruluk: %{accuracy:.1f} - Birlikte daha çok çalışalım! 💪\n", 'red')

        self.results_text.insert(tk.END, f"📚 Hızım: Dakikada {speed:.1f} kelime\n\n", 'blue')

        if analysis['hesitations'] or analysis['mispronunciations']:
            self.results_text.insert(tk.END, "🎯 Geliştirebileceğim Noktalar:\n", 'underline_font')

            if analysis['hesitations']:
                self.results_text.insert(tk.END, "🗣️ Tekrarladığım Kelimeler:\n", 'purple')
                for h in analysis['hesitations']:
                    self.results_text.insert(tk.END, f"• {h['word']} ({h['type']})\n", 'yellow')

            if analysis['mispronunciations']:
                self.results_text.insert(tk.END, "📝 Yanlış Okuduğum Kelimeler:\n", 'purple')
                for word in analysis['mispronunciations']:
                    self.results_text.insert(tk.END, f"• {word}\n", 'red')

        self.notebook.select(1)

    def finalize_reading(self, use_stored_segments=False):
        if self.is_streaming:
            self.stop_streaming()

        if self.all_segments:
            if use_stored_segments:
                analysis = self.analyze_reading()
            else:
                analysis = self.analyze_reading()

            self.format_analysis_results(analysis)
            self.all_segments.clear()

    def toggle_custom_text(self):
        self.text_var.set('')
        self.text_area.config(state='normal')
        self.text_area.delete(1.0, tk.END)
        self.text_area.focus()

    def update_text(self):
        if self.is_streaming:
            messagebox.showinfo("Uyarı", "Okuma devam ederken yeni bir metin seçemezsiniz!")
            return

        selected = self.text_var.get()
        if selected in self.sample_texts:
            self.text_area.config(state='normal')
            self.text_area.delete(1.0, tk.END)
            self.text_area.insert(tk.END, self.sample_texts[selected])
            self.text_area.config(state='disabled')

    def show_settings(self):
        settings_window = tk.Toplevel(self.root)
        settings_window.title('Ayarlar')
        settings_window.geometry('400x400')

        ttk.Label(settings_window, text='Host:').pack(pady=5)
        host_entry = ttk.Entry(settings_window, width=30)
        host_entry.insert(0, self.config['host'])
        host_entry.pack(pady=5)

        ttk.Label(settings_window, text='Port:').pack(pady=5)
        port_entry = ttk.Entry(settings_window, width=30)
        port_entry.insert(0, str(self.config['port']))
        port_entry.pack(pady=5)

        ttk.Label(settings_window, text='Model:').pack(pady=5)
        model_entry = ttk.Entry(settings_window, width=30)
        model_entry.insert(0, self.config['model'])
        model_entry.pack(pady=5)

        ttk.Label(settings_window, text='Dil:').pack(pady=5)
        lang_entry = ttk.Entry(settings_window, width=30)
        lang_entry.insert(0, self.config['lang'])
        lang_entry.pack(pady=5)

        def save_settings():
            self.config['host'] = host_entry.get()
            self.config['port'] = int(port_entry.get())
            self.config['model'] = model_entry.get()
            self.config['lang'] = lang_entry.get()
            self.save_config()
            settings_window.destroy()

        ttk.Button(settings_window, text='Kaydet', command=save_settings).pack(pady=10)

    def toggle_streaming(self):
        if not self.is_streaming:
            self.start_streaming()
        else:
            self.stop_streaming()

    def start_streaming(self):
        if self.is_streaming:
            return

        self.is_streaming = True
        self.record_button.config(text='⏹️ Bitir')
        self.results_text.delete(1.0, tk.END)

        self.text_area.config(state='normal')
        raw_text = self.text_area.get("1.0", tk.END)
        lines = []
        for line in raw_text.splitlines():
            if not line.strip().startswith("OKUNULAN:"):
                lines.append(line)
        cleaned_text = "\n".join(lines)
        self.reference_words = self.tokenize_text(cleaned_text.strip())
        self.next_word_index = 0

        for tag_name in self.text_area.tag_names():
            self.text_area.tag_remove(tag_name, "1.0", tk.END)

        content = self.text_area.get("1.0", tk.END)
        idx = content.find("OKUNULAN:")
        if idx != -1:
            row = content[:idx].count('\n') + 1
            next_newline = content.find('\n', idx)
            if next_newline == -1:
                next_newline = len(content)
            self.text_area.delete(f"{row}.0", f"{row + 1}.0")

        while True:
            last_char = self.text_area.get("end-2c", "end-1c")
            if last_char in ["\n", " "]:
                self.text_area.delete("end-2c", "end-1c")
            else:
                break

        self.text_area.insert(tk.END, "\n\nOKUNULAN: ")
        self.okunulan_start_index = self.text_area.index(tk.END)
        self.text_area.insert(tk.END, "...\n")

        self.text_area.config(state='disabled')

        for rb in self.radio_buttons:
            rb.config(state='disabled')
        self.custom_button.config(state='disabled')

        def run_client():
            self.transcription_client = CaptureTranscriptionClient(
                host=self.config['host'],
                port=self.config['port'],
                lang=self.config['lang'],
                model=self.config['model'],
                use_vad=self.config['use_vad'],
                translate=False,
                text_callback=self.handle_live_transcript
            )
            self.transcription_client()

        self.stream_thread = threading.Thread(target=run_client, daemon=True)
        self.stream_thread.start()

        prep_window = tk.Toplevel(self.root)
        prep_window.title('Hazırlanıyor')
        prep_window.geometry('300x150')
        x = self.root.winfo_x() + (self.root.winfo_width() - 300) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 150) // 2
        prep_window.geometry(f'+{x}+{y}')

        message_label = ttk.Label(
            prep_window,
            text='Sunucuya bağlanılıyor...\nLütfen bekleyin...',
            font=('Comic Sans MS', 12)
        )
        message_label.pack(expand=True)

        def wait_for_server_ready():
            while True:
                if (self.transcription_client
                        and self.transcription_client.client
                        and self.transcription_client.client.recording):
                    break
                time.sleep(0.2)

            def on_ready():
                message_label.config(text='Sunucu hazır, başlayabilirsiniz!')
                self.root.after(1000, prep_window.destroy)

            self.root.after(0, on_ready)

        threading.Thread(target=wait_for_server_ready, daemon=True).start()

    def stop_streaming(self):
        if not self.is_streaming:
            return

        self.is_streaming = False
        self.record_button.config(text='🎤 Okumaya Başla')

        if self.transcription_client and self.transcription_client.client:
            try:
                self.transcription_client.client.close_websocket()
            except:
                pass
        self.transcription_client = None

        for rb in self.radio_buttons:
            rb.config(state='normal')
        self.custom_button.config(state='normal')

        self.text_area.config(state='normal')

        self.finalize_reading(use_stored_segments=True)

    def handle_live_transcript(self, segments):
        new_text = segments[-1]["text"].strip()

        phrases_to_check = ["Altyazı M.K.", "İzlediğiniz için teşekkür ederim.", "abone ol"]

        if any(phrase.lower() in new_text.lower() for phrase in phrases_to_check):
            return

        self.all_segments = segments.copy()

        spoken_words = self.tokenize_text(new_text)

        self.root.after(0, lambda: self.update_currently_said_text(new_text))

        for w in spoken_words:
            if self.next_word_index >= len(self.reference_words):
                break

            ref_word = self.reference_words[self.next_word_index]
            if self.normalize_word(w) == self.normalize_word(ref_word):
                self.root.after(0, self.highlight_word, self.next_word_index, True)
                self.next_word_index += 1
            else:
                self.root.after(0, self.highlight_word, self.next_word_index, False)

        if self.next_word_index >= len(self.reference_words):
            self.root.after(0, lambda: self.finalize_reading(use_stored_segments=True))

    def update_currently_said_text(self, partial_text: str):
        self.text_area.config(state='normal')

        text_content = self.text_area.get("1.0", tk.END)
        okunulan_pos = text_content.find("OKUNULAN:")

        if okunulan_pos != -1:
            row = text_content[:okunulan_pos].count('\n') + 1
            col = okunulan_pos - text_content[:okunulan_pos].rfind('\n') - 1
            start_idx = f"{row}.{col + 10}"

            self.text_area.delete(start_idx, tk.END)
            self.text_area.insert(tk.END, f" {partial_text}\n")

        self.text_area.config(state='disabled')
        self.text_area.see(tk.END)

    def highlight_word(self, word_index: int, correct: bool):
        self.text_area.config(state='normal')

        start_idx, end_idx = self.find_word_position_in_text_area(word_index)
        if start_idx is not None and end_idx is not None:
            tag = 'high_conf' if correct else 'low_conf'
            self.text_area.tag_remove('high_conf', start_idx, end_idx)
            self.text_area.tag_remove('low_conf', start_idx, end_idx)
            self.text_area.tag_add(tag, start_idx, end_idx)

        self.text_area.config(state='disabled')

    def find_word_position_in_text_area(self, word_index: int):
        target_word = self.reference_words[word_index]
        text_content = self.text_area.get("1.0", tk.END)
        tokens = text_content.split()

        if word_index < len(tokens):
            word_to_find = tokens[word_index]

            pos = text_content.find(word_to_find)
            if pos == -1:
                return None, None

            row = text_content[:pos].count('\n') + 1
            last_newline_idx = text_content[:pos].rfind('\n')
            if last_newline_idx == -1:
                col = pos
            else:
                col = pos - (last_newline_idx + 1)

            start_index = f"{row}.{col}"
            end_index = f"{row}.{col + len(word_to_find)}"
            return start_index, end_index
        else:
            return None, None

    @staticmethod
    def tokenize_text(text: str):
        tokens = text.strip().split()
        return tokens

    @staticmethod
    def normalize_word(word: str):
        return re.sub(r"[^\wıüğşöçİÜĞŞÖÇ]", "", word, flags=re.UNICODE).lower()

    def setup_styles(self):
        style = ttk.Style()
        style.configure('Kid.TButton',
                        font=('Comic Sans MS', 12),
                        padding=10,
                        background='#FFB6C1')
        style.configure('Recording.TButton',
                        background='#FF6B6B',
                        foreground='white')
        style.configure('TLabelframe')
        style.configure('TNotebook')

    def on_closing(self):
        if self.is_streaming:
            self.stop_streaming()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = DyslexiaFrontendApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
