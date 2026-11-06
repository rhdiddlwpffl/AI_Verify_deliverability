# 메인 화면 이미지(frontend/src/assets/hero.png) 생성에 쓴 스크립트.
# 서비스 코드가 아니라 이미지 제작용 도구이며, 배포(Render/Vercel)와는 관계가 없다.
# 실행 환경: CUDA GPU가 있는 Jupyter 노트북 (IPython의 display, torch, diffusers 필요).
# 결과 이미지는 results/sdxl/ 에 저장된다.

import time, uuid, json
from pathlib import Path
import torch
from diffusers import AutoPipelineForText2Image
from IPython.display import display

# ---- 바꿔 볼 값 ----
PROMPT = 'Minimal flat illustration, wide banner. A sheet of paper with several lines of text, a few sentences softly highlighted in blue, orange and purple, and a magnifying glass hovering over one highlighted sentence. Small speech-bubble shape in the corner suggesting an AI answer being inspected. Clean off-white background, soft rounded shapes, generous empty space on the left for a title. Calm, trustworthy, editorial style, no text, no letters, no checkmarks, no cross marks, no red or green colors. 1200x630.'
SEED = 42
STEPS = 1          # SDXL-Turbo는 1~4면 충분합니다
WIDTH, HEIGHT = 512, 512
# --------------------

def prepare_model(repo_id, folder, marker, patterns):
    from huggingface_hub import snapshot_download
    shared = Path('/opt/models') / folder
    if (shared / marker).is_file():
        return str(shared)
    target = Path.home() / 'models' / folder
    done = target / '.download_complete'
    if done.is_file():
        return str(target)
    target.mkdir(parents=True, exist_ok=True)
    print('모델을 내려받습니다(처음 한 번, 몇 분 걸릴 수 있음):', target)
    snapshot_download(repo_id, local_dir=str(target), allow_patterns=patterns)
    done.touch()
    return str(target)

if not torch.cuda.is_available():
    raise RuntimeError('CUDA GPU를 사용할 수 없습니다.')

# 모델은 한 번만 불러오고, 프롬프트만 바꿔 재실행할 때는 재사용합니다.
if 'sdxl_pipe' not in globals():
    sdxl_path = prepare_model('stabilityai/sdxl-turbo', 'sdxl-turbo', 'model_index.json',
                              ['*.json', '*.txt', '*.fp16.safetensors'])
    sdxl_pipe = AutoPipelineForText2Image.from_pretrained(
        sdxl_path, torch_dtype=torch.float16, variant='fp16', local_files_only=True
    ).to('cuda')
    print('SDXL Turbo 준비 완료')

generator = torch.Generator(device='cpu').manual_seed(SEED)
start = time.perf_counter()
with torch.inference_mode():
    image = sdxl_pipe(prompt=PROMPT, generator=generator, num_inference_steps=STEPS,
                      height=HEIGHT, width=WIDTH, guidance_scale=0.0).images[0]
torch.cuda.synchronize()
seconds = round(time.perf_counter() - start, 2)

out = Path('results/sdxl'); out.mkdir(parents=True, exist_ok=True)
stem = 'text2img_' + uuid.uuid4().hex[:12]
image.save(out / f'{stem}.png')
(out / f'{stem}.json').write_text(json.dumps(
    {'prompt': PROMPT, 'seed': SEED, 'steps': STEPS, 'width': WIDTH, 'height': HEIGHT, 'seconds': seconds},
    ensure_ascii=False, indent=2), encoding='utf-8')

print(f'{seconds}초 | 저장: {out / (stem + ".png")}')
display(image)
