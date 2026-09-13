import json, pathlib, subprocess
import imageio_ffmpeg
p = pathlib.Path(__file__).resolve().parent
frames = json.loads((p/'frames.json').read_text())
lines = ['ffconcat version 1.0']
for i, f in enumerate(frames):
    duration = frames[i+1]['time']-f['time'] if i+1<len(frames) else 2
    lines += ["file '"+f['file']+"'",f'duration {max(.02,duration):.6f}']
lines += ["file '"+frames[-1]['file']+"'"]
(p/'video.ffconcat').write_text('\n'.join(lines)+'\n')
cmd=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','warning','-y','-safe','0','-i',str(p/'video.ffconcat'),'-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2,fps=15','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(p/'anker-10-rounds.mp4')]
subprocess.run(cmd,check=True)
print(json.dumps({'video':str(p/'anker-10-rounds.mp4'),'bytes':(p/'anker-10-rounds.mp4').stat().st_size,'captured_frames':len(frames),'duration':frames[-1]['time']-frames[0]['time']+2}))
