Smart trim with FFMPEG
===========================

This tool implements smart trim using python-ffmpeg.
It allows precise trimming of a video with minimum re-encoding for minimum quality loss. 

For more info about smart trim, see [here](https://superuser.com/questions/1039083/smart-trim-an-h-264-mp4-video-file-in-ffmpeg).

### Installation

```bash
pip3 install ffmpeg_smart_trim
```

### Usage

```bash
python3 -m ffmpeg_smart_trim.trim in.mp4 --start_time 12.345 --end_time 67.890 -output out.mp4
```
