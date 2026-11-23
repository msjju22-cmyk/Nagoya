"""사진/영상을 암호화해서 GitHub 페이지용으로 올릴 준비를 한다.
사용: python3 add_photos.py <repo_dir> <파일...>
필요: repo/photokey.json (페이지의 '사진 잠금 설정'에서 만든 열쇠 코드)
- 사진: 방향 보정, 긴 변 1600px + 640px 썸네일
- 영상: H.264 MP4(긴 변 1280) + 첫 장면 썸네일
- 촬영시각·GPS를 읽어 사진 목록에 넣고, 목록과 파일을 모두 암호화
  (파일마다 AES-256-GCM 키, 목록은 묶음 키로 암호화 후 공개키 RSA-OAEP로 감쌈)
"""
import sys, os, json, hashlib, subprocess, re, datetime, base64, io, secrets, tempfile, time
from PIL import Image, ImageOps
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
try:
    import pillow_heif; pillow_heif.register_heif_opener()
except ImportError:
    pass

repo = sys.argv[1]; files = sys.argv[2:]
b64 = lambda b: base64.b64encode(b).decode()
pk = json.load(open(os.path.join(repo, 'photokey.json')))
pub = serialization.load_der_public_key(base64.b64decode(pk['pub']))
mdir = os.path.join(repo, 'media'); os.makedirs(mdir, exist_ok=True)
hpath = os.path.join(mdir, 'hashes.txt')
have = set(open(hpath).read().split()) if os.path.exists(hpath) else set()
ipath = os.path.join(mdir, 'index.json')
index = json.load(open(ipath)) if os.path.exists(ipath) else []

def kst_ms(y, mo, d, h, mi, s):
    return int(datetime.datetime(y, mo, d, h, mi, s, tzinfo=datetime.timezone(datetime.timedelta(hours=9))).timestamp() * 1000)

def img_meta(im):
    out = {}; ex = im.getexif()
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

def enc_file(data):
    key = AESGCM.generate_key(256); iv = secrets.token_bytes(12)
    name = secrets.token_hex(10) + '.bin'
    open(os.path.join(mdir, name), 'wb').write(iv + AESGCM(key).encrypt(iv, data, None))
    return 'media/' + name, b64(key)

def jpeg(im, size, q):
    c = im.copy(); c.thumbnail((size, size)); bio = io.BytesIO(); c.save(bio, 'JPEG', quality=q, optimize=True, progressive=True); return bio.getvalue()

entries = []
for f in files:
    h = hashlib.sha1(open(f, 'rb').read()).hexdigest()[:16]
    if h in have:
        print('skip (already added):', f); continue
    ext = f.rsplit('.', 1)[-1].lower()
    if ext in ('mov', 'mp4', 'm4v', 'webm', '3gp'):
        meta = vid_meta(f)
        with tempfile.TemporaryDirectory() as td:
            mp4 = os.path.join(td, 'v.mp4'); poster = os.path.join(td, 'p.jpg')
            subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', f, '-vf', "scale='if(gt(iw,ih),min(1280,iw),-2)':'if(gt(iw,ih),-2,min(1280,ih))'",
                            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '26', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k',
                            '-movflags', '+faststart', mp4], check=True)
            subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', '0.3', '-i', mp4, '-frames:v', '1', poster], check=False)
            fpath, fk = enc_file(open(mp4, 'rb').read())
            e = {'type': 'video', 'mime': 'video/mp4', 'f': fpath, 'k': fk, **meta}
            if os.path.exists(poster):
                e['tf'], e['tk'] = enc_file(jpeg(Image.open(poster).convert('RGB'), 640, 78))
    else:
        im = Image.open(f); meta = img_meta(im); im = ImageOps.exif_transpose(im).convert('RGB')
        fpath, fk = enc_file(jpeg(im, 1600, 84)); tpath, tk = enc_file(jpeg(im, 640, 78))
        e = {'type': 'image', 'mime': 'image/jpeg', 'f': fpath, 'k': fk, 'tf': tpath, 'tk': tk, **meta}
    entries.append(e); have.add(h)
    print('added', os.path.basename(f), {k: e[k] for k in ('t', 'lat', 'lng') if k in e})

if entries:
    ck = AESGCM.generate_key(256); iv = secrets.token_bytes(12)
    ct = AESGCM(ck).encrypt(iv, json.dumps(entries, ensure_ascii=False).encode(), None)
    wk = pub.encrypt(ck, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    bname = f'b{int(time.time())}.json'
    json.dump({'v': 1, 'wk': b64(wk), 'iv': b64(iv), 'ct': b64(ct)}, open(os.path.join(mdir, bname), 'w'))
    index.append(bname); json.dump(index, open(ipath, 'w'))
    open(hpath, 'w').write('\n'.join(sorted(have)))
print(f'{len(entries)} file(s) added in this batch; batches total {len(index)}')
