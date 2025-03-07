import time
from whisper_live.client import Client, TranscriptionClient
from typing import Callable, Optional


class CaptureClient(Client):
    def __init__(self, *args, text_callback: Optional[Callable[[str], None]] = None, **kwargs):
        kwargs['log_transcription'] = False
        super().__init__(*args, **kwargs)
        self.text_callback = text_callback
        self.last_text = None

    def process_segments(self, segments):
        current_text = segments[-1]["text"].strip()

        if current_text != self.last_text:
            if self.text_callback:
                self.text_callback(segments)
            self.last_text = current_text

        for i, seg in enumerate(segments):
            if i == len(segments) - 1:
                self.last_segment = seg
            elif (self.server_backend == "faster_whisper" and
                  (not self.transcript or
                   float(seg['start']) >= float(self.transcript[-1]['end']))):
                self.transcript.append(seg)

        if self.last_received_segment is None or self.last_received_segment != segments[-1]["text"]:
            self.last_response_received = time.time()
            self.last_received_segment = segments[-1]["text"]


class CaptureTranscriptionClient(TranscriptionClient):
    def __init__(self, *args, text_callback: Optional[Callable[[str], None]] = None, **kwargs):
        self.client = CaptureClient(*args, text_callback=text_callback, **kwargs)
        super(TranscriptionClient, self).__init__([self.client])
