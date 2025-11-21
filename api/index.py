from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import functools
import traceback
import json

app = Flask(__name__)
CORS(app)

# ================= 配置区域 =================
NETEASE_API_BASE = "https://music.ccyacg.xyz"
MY_API_KEY = "114514" 
# ===========================================

# --- 统一响应格式 ---
def response_json(data=None, code=200, msg="操作成功"):
    resp_dict = {
        "code": code,
        "message": msg, 
        "data": data
    }
    # 打印响应日志
    try:
        print("\n" + "="*30 + " SENDING RESPONSE " + "="*30)
        print(f"[Status Code]: {code}")
        log_content = json.dumps(resp_dict, ensure_ascii=False, default=str)
        if len(log_content) > 1000:
            print(f"[Body (Truncated)]: {log_content[:1000]}...")
        else:
            print(f"[Body]: {log_content}")
        print("="*78 + "\n")
    except Exception:
        pass
    return jsonify(resp_dict)

# --- 调试辅助：请求日志 ---
def log_request_debug():
    print("\n" + "="*30 + " NEW REQUEST " + "="*30)
    print(f"[Path]: {request.path}")
    print(f"[Method]: {request.method}")
    # print(f"[Headers]:\n{request.headers}") # 嫌日志太长可以注释掉Header
    raw_data = request.get_data(as_text=True)
    print(f"[Raw Body String]: {raw_data}")
    print("="*73 + "\n")

# --- 中间件：ApiKey 验证 ---
def require_apikey(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        log_request_debug()
        if not MY_API_KEY:
            return f(*args, **kwargs)
        request_key = request.headers.get('ApiKey')
        if request_key != MY_API_KEY:
             print(f"!!! API Key 验证失败. Receive: {request_key}")
             return response_json(code=400, msg=f"API Key 无效. Receive: {request_key}")
        return f(*args, **kwargs)
    return decorated

# ================= 接口实现 =================

@app.route('/SearchMusicList', methods=['POST'])
@require_apikey
def search_music_list():
    try:
        print(">>> [Logic] 开始解析参数...")
        payload = request.get_json(force=True, silent=True) or request.values.to_dict() or {}
        print(f">>> [Logic] 解析到的 Payload: {payload}")

        # === 修复点 1: 兼容大小写 ===
        # 优先找 'Keyword', 找不到就找 'keyword'
        keyword = payload.get('Keyword') or payload.get('keyword')
        
        # 优先找 'Page', 找不到就找 'page', 实在没有默认为 1
        page = payload.get('Page') or payload.get('page') or 1
        # ==========================

        if not keyword:
            return response_json(code=400, msg="参数 Keyword 不能为空")

        limit = 20
        try:
            offset = (int(page) - 1) * limit
        except ValueError:
            offset = 0

        target_url = f"{NETEASE_API_BASE}/cloudsearch"
        # print(f">>> [Logic] 请求网易云接口: {target_url}")
        
        resp = requests.get(target_url, params={
            "keywords": keyword,
            "limit": limit,
            "offset": offset,
            "type": 1
        })
        n_data = resp.json()

        results = []
        if n_data.get('code') == 200 and 'result' in n_data:
            for song in n_data['result'].get('songs', []):
                duration_sec = int(song.get('dt', 0) / 1000)
                results.append({
                    "name": song['name'],
                    "album": song['al']['name'] if song.get('al') else "",
                    "duration": duration_sec,
                    "singer": song['ar'][0]['name'] if song.get('ar') else "Unknown",
                    "id": str(song['id'])
                })

        return response_json(data=results)

    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"!!! [Error] SearchMusicList 崩溃:\n{error_trace}")
        return response_json(code=500, msg=f"Server Error: {str(e)}")


@app.route('/GetMusicDetail', methods=['GET'])
@require_apikey
def get_music_detail():
    try:
        # GET 请求不需要改，因为 request.args 不区分大小写吗？不，通常 URL 参数也区分
        # 为了保险，这里也改一下
        song_id = request.args.get('id') or request.args.get('Id') or request.args.get('ID')
        
        if not song_id:
            return response_json(code=400, msg="参数 id 不能为空")

        target_url = f"https://music.163.com/song?id={song_id}"
        redirect_api = f"https://biliplayer.91vrchat.com/player/?url={target_url}"
        
        real_url = ""
        try:
            r = requests.get(redirect_api, allow_redirects=True, stream=True, timeout=10)
            real_url = r.url
            r.close() 
        except Exception as url_err:
            print(f"!!! [Error] 解析直链失败: {url_err}")

        lrc_api = f"{NETEASE_API_BASE}/lyric"
        lrc_resp = requests.get(lrc_api, params={"id": song_id})
        lrc_data = lrc_resp.json()
        
        lyric_text = ""
        if lrc_data.get('code') == 200:
            lyric_text = lrc_data.get('lrc', {}).get('lyric', "")

        if not real_url or "biliplayer" in real_url: 
            return response_json(code=400, msg="无法解析歌曲直链，请重试")

        return response_json(data={
            "url": real_url,
            "lyric": lyric_text,
            "id": song_id
        })

    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"!!! [Error] GetMusicDetail 崩溃:\n{error_trace}")
        return response_json(code=500, msg=str(e))


@app.route('/SearchMusicRecommendedList', methods=['POST'])
@require_apikey
def search_recommended():
    try:
        print(">>> [Logic] 进入推荐搜索...")
        payload = request.get_json(force=True, silent=True) or request.values.to_dict() or {}

        # === 修复点 2: 兼容大小写 ===
        keyword = payload.get('Keyword') or payload.get('keyword')
        size = payload.get('size') or payload.get('Size') or 10
        # ==========================

        if not keyword:
            return response_json(code=400, msg="参数 Keyword 不能为空")

        target_url = f"{NETEASE_API_BASE}/cloudsearch"
        resp = requests.get(target_url, params={
            "keywords": keyword,
            "limit": size,
            "type": 1
        })
        n_data = resp.json()

        results = []
        if n_data.get('code') == 200 and 'result' in n_data:
            for song in n_data['result'].get('songs', []):
                duration_sec = int(song.get('dt', 0) / 1000)
                results.append({
                    "name": song['name'],
                    "album": song['al']['name'] if song.get('al') else "",
                    "duration": duration_sec,
                    "singer": song['ar'][0]['name'] if song.get('ar') else "Unknown",
                    "id": str(song['id'])
                })

        return response_json(data=results)

    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"!!! [Error] SearchMusicRecommendedList 崩溃:\n{error_trace}")
        return response_json(code=500, msg=str(e))

# if __name__ == '__main__':
#    app.run(debug=True, port=5000)
