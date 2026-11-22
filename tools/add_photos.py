"""사진/영상을 받아 GitHub 페이지용으로 정리한다.
사용: python3 add_photos.py <repo_dir> <파일...>
- 사진: 방향 보정, 긴 변 1600px JPEG + 600px 썸네일, EXIF 촬영시각·GPS 추출
- 영상: H.264 MP4(긴 변 1280)로 변환, 촬영시각·위치 메타데이터 추출
- photos.json에 추가 (일정 칸 매칭은 페이지가 시각·위치로 자동 처리)
"""
import sys, os, json, hashlib, subprocess, re, datetime
from PIL import Image, ImageOps
try:
    import pillow_heif; pillow_heif.register_heif_opener()
except ImportError:
    pass

repo = sys.argv[1]; files = sys.argv[2:]
pdir = os.path.join(repo, 'photos'); tdir = os.path.join(pdir, 'thumbs')
os.makedirs(tdir, exist_ok=True)
jpath = os.path.join(repo, 'photos.json')
data = json.load(open(jpath)) if os.path.exists(jpath) else []
have = {d.get('hash') for d in data}

def kst_ms(y, mo, d, h, mi, s):  # 일본 현지(=KST, +9) 시각 → UTC ms
    return int(datetime.datetime(y, mo, d, h, mi, s, tzinfo=datetime.timezone(datetime.timedelta(hours=9))).timestamp() * 1000)

def img_meta(im):
    out = {}
    ex = im.getexif()
    dt = ex.get_ifd(0x8769).get(0x9003) or ex.get(0x0132)
    if dt:
        m = re.match(r'(\d{4}):(\d\d):(\d\d) (\d\d):(\d\d):(\d\d)', str(dt))
        if m: out['t'] = kst_ms(*map(int, m.groups()))
    g = ex.get_ifd(0x8825)
    if g.get(2) and g.get(4):
        f = lambda v: float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
        lat, lng = f(g[2]), f(g[4])
        if g.get(1) == 'S': lat = -lat
        if g.get(3) == 'W': lng = -lng
        out['lat'], out['lng'] = round(lat, 6), round(lng, 6)
    return out

def vid_meta(path):
    out = {}
    j = json.loads(subprocess.run(['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', path], capture_output=True, text=True).stdout or '{}')
    tags = {k.lower(): v for k, v in j.get('format', {}).get('tags', {}).items()}
    ct = tags.get('com.apple.quicktime.creationdate') or tags.get('creation_time')
    if ct:
        try: out['t'] = int(datetime.datetime.fromisoformat(ct.replace('Z', '+00:00')).timestamp() * 1000)
        except ValueError: pass
    loc = tags.get('com.apple.quicktime.location.iso6709') or tags.get('location')
    if loc:
        m = re.match(r'([+-]\d+\.\d+)([+-]\d+\.\d+)', loc)
        if m: out['lat'], out['lng'] = float(m.group(1)), float(m.group(2))
    return out

added = 0
for f in files:
    h = hashlib.sha1(open(f, 'rb').read()).hexdigest()[:12]
    if h in have:
        print('skip (already added):', f); continue
    ext = f.rsplit('.', 1)[-1].lower()
    if ext in ('mov', 'mp4', 'm4v', 'webm', '3gp'):
        meta = vid_meta(f); name = f'v_{h}.mp4'
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', f, '-vf', "scale='if(gt(iw,ih),min(1280,iw),-2)':'if(gt(iw,ih),-2,min(1280,ih))'",
                        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '26', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k',
                        '-movflags', '+faststart', os.path.join(pdir, name)], check=True)
        rec = {'src': 'photos/' + name, 'type': 'video', **meta, 'hash': h}
    else:
        im = Image.open(f); meta = img_meta(im); im = ImageOps.exif_transpose(im).convert('RGB')
        name = f'p_{h}.jpg'
        big = im.copy(); big.thumbnail((1600, 1600)); big.save(os.path.join(pdir, name), quality=84, optimize=True, progressive=True)
        th = im.copy(); th.thumbnail((640, 640)); th.save(os.path.join(tdir, name), quality=78, optimize=True)
        rec = {'src': 'photos/' + name, 'thumb': 'photos/thumbs/' + name, 'type': 'image', **meta, 'hash': h}
    data.append(rec); have.add(h); added += 1
    print('added', f, '->', rec['src'], {k: rec[k] for k in ('t', 'lat', 'lng') if k in rec})
data.sort(key=lambda d: d.get('t') or 0)
json.dump(data, open(jpath, 'w'), ensure_ascii=False, indent=0)
print(f'{added} file(s) added, total {len(data)}')
