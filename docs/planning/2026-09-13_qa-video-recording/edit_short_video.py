import pathlib,subprocess,json,imageio_ffmpeg
p=pathlib.Path(__file__).resolve().parent
# Keep observed question/action/answer moments; drop idle holds and late navigation.
segments=[(0,3),(10,15),(22,26),(28,33),(40,45),(63,70),(86,94),(99,104),(111,116),(120,126),(147,152),(156,162),(174,181),(187,191),(195,201),(211,217),(228,234),(240,247),(254,260),(319,325)]
speed=2.2
filters=[]
for i,(a,b) in enumerate(segments):
 filters.append(f'[0:v]trim=start={a}:end={b},setpts=(PTS-STARTPTS)/{speed}[v{i}]')
filters.append(''.join(f'[v{i}]' for i in range(len(segments)))+f'concat=n={len(segments)}:v=1:a=0,fps=30,format=yuv420p[out]')
(p/'short-edit.json').write_text(json.dumps({'segments':segments,'speed':speed,'planned_seconds':sum(b-a for a,b in segments)/speed},indent=2))
cmd=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','warning','-y','-i',str(p/'anker-10-rounds.mp4'),'-filter_complex',';'.join(filters),'-map','[out]','-an','-c:v','libx264','-preset','fast','-crf','19','-movflags','+faststart',str(p/'anker-10-rounds-short.mp4')]
subprocess.run(cmd,check=True)
print('Expected seconds:',sum(b-a for a,b in segments)/speed)
