import os
import shlex
import shutil
from decimal import Decimal
from tempfile import mkdtemp

import ffmpeg


class TrimVideo:
    def __init__(self, video_path, temp_dir=None, time_range: (Decimal, Decimal) = None):
        probe = ffmpeg.probe(video_path, skip_frame="nokey", show_entries="frame=pkt_pts_time", select_streams="v:0")
        self.vcodec = ffmpeg.probe(video_path, select_streams="v:0")['streams'][0]['codec_name']
        self.acodec = ffmpeg.probe(video_path, select_streams="a:0")['streams'][0]['codec_name']
        self.key_frame_timestamps = [Decimal(frame['pkt_pts_time']) for frame in probe['frames']]
        self.duration = Decimal(probe['streams'][0]['duration'])
        if time_range is None:
            self.input_file: ffmpeg.nodes.FilterableStream = ffmpeg.input(video_path)
            self.time_range = (Decimal(0), self.duration)
        else:
            start_key_frame = self.find_before_timestamp(time_range[0])
            end_key_frame = self.find_after_timestamp(time_range[1])
            self.input_file: ffmpeg.nodes.FilterableStream = \
                ffmpeg.input(video_path, ss=start_key_frame, to=end_key_frame, copyts=None)
            self.time_range = time_range
        if temp_dir is not None:
            self.temp_dir = mkdtemp(dir=temp_dir)
        else:
            self.temp_dir = mkdtemp()

    def find_before_timestamp(self, timestamp):
        last_timestamp = self.key_frame_timestamps[0]
        for key_frame_timestamp in self.key_frame_timestamps:
            if key_frame_timestamp > timestamp:
                break
            last_timestamp = key_frame_timestamp
        return last_timestamp

    def find_after_timestamp(self, timestamp):
        last_timestamp = self.duration
        for key_frame_timestamp in reversed(self.key_frame_timestamps):
            if key_frame_timestamp < timestamp:
                break
            last_timestamp = key_frame_timestamp
        return last_timestamp

    def generate_trim(self, start_time, end_time, prefix=''):
        if start_time < self.time_range[0]:
            start_time = self.time_range[0]
        if end_time > self.time_range[1]:
            end_time = self.time_range[1]
        fast_trims = []
        slow_trims = []
        files = []

        start_time = Decimal(start_time)
        start_key_frame = self.find_after_timestamp(start_time)
        end_time = Decimal(end_time)
        end_key_frame = self.find_before_timestamp(end_time)

        def trim(start, end, path: str, copy: bool):
            if copy:
                return ffmpeg.output(self.input_file, path, c='copy', ss=start, to=end)
            else:
                return ffmpeg.output(self.input_file, path, acodec=self.acodec, vcodec=self.vcodec, ss=start, to=end)

        if start_key_frame > end_key_frame:  # start_time and end_time with in same key_frame
            output = os.path.join(self.temp_dir, f"{prefix}_output.ts")
            slow_trims += [trim(start_time, end_time, output, copy=False)]
            files += [output]
        else:
            start_valid = start_time != start_key_frame
            end_valid = end_time != end_key_frame
            start_file = os.path.join(self.temp_dir, f"{prefix}_start.ts")
            end_file = os.path.join(self.temp_dir, f"{prefix}_end.ts")
            if start_valid:
                slow_trims += [trim(start_time, start_key_frame, start_file, copy=False)]
            if end_valid:
                slow_trims += [trim(end_key_frame, end_time, end_file, copy=False)]
            if start_key_frame == end_key_frame:  # there is no keyframes between start and end time
                if start_valid:
                    files += [start_file]
                if end_valid:
                    files += [end_file]
            else:  # most common, there are keyframes between start and end
                middle_file = os.path.join(self.temp_dir, f"{prefix}_middle.ts")
                fast_trims += [trim(start_key_frame, end_key_frame, middle_file, copy=True)]
                if start_valid:
                    files += [start_file]
                files += [middle_file]
                if end_valid:
                    files += [end_file]

        return files, fast_trims, slow_trims

    def generate_merge_file(self, paths, prefix=''):
        merge_path = os.path.join(self.temp_dir, f"{prefix}_concat.txt")
        with open(merge_path, "w+") as merge_file:
            for path in paths:
                merge_file.write(f'file {shlex.quote(path)}\n')
        return merge_path

    def generate_merge(self, paths, output_path, prefix='', merge_file_path=None):
        if merge_file_path is None:
            merge_file_path = self.generate_merge_file(paths, prefix)
        merge_input = ffmpeg.input(merge_file_path, f='concat', safe=0)
        return ffmpeg.output(merge_input, output_path, c='copy', avoid_negative_ts=1)

    def clean_temp(self):
        shutil.rmtree(self.temp_dir)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Smart trim video using ffmpeg')
    parser.add_argument('--start_time', type=str, help='start time')
    parser.add_argument('--end_time', type=str, help='end time')
    parser.add_argument('--output', type=str, help='output file path')
    parser.add_argument('video', type=str, help='path to video to be trim')

    args = parser.parse_args()
    input_start_time = Decimal(args.start_time)
    input_end_time = Decimal(args.end_time)
    print("Parsing video file...")
    video = TrimVideo(args.video, time_range=(input_start_time, input_end_time))
    trim_files, fast_trims_cmd, slow_trims_cmd = video.generate_trim(input_start_time, input_end_time)
    print("trimting video file...")
    if len(fast_trims_cmd) > 0:
        ffmpeg.merge_outputs(*fast_trims_cmd).run(overwrite_output=True)
        # print(ffmpeg.merge_outputs(*fast_trims_cmd).compile())
    if len(slow_trims_cmd) > 0:
        ffmpeg.merge_outputs(*slow_trims_cmd).run(overwrite_output=True)
        # print(ffmpeg.merge_outputs(*slow_trims_cmd).compile())
    merge_cmd = video.generate_merge(trim_files, args.output)
    # print(merge_cmd.compile())
    print("Merging video file...")
    merge_cmd.run(overwrite_output=True)
    video.clean_temp()
