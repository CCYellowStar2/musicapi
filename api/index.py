from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import functools
import traceback # 引入这个用于打印详细报错堆栈
import json

app = Flask(__name__)
CORS(app)

# ================= 配置区域 =================
NETEASE_API_BASE = "https://music.ccyacg.xyz"
MY_API_KEY = "114514" 
# ===========================================

# --- 统一响应格式 ---
def response_json(data=None, code=200, msg="操作成功"):
    return jsonify({
        "code": code,
        "message": msg, 
        "data": data
    })

# --- 日志辅助函数 ---
def log_request_debug():
    """打印请求的详细信息，用于排查机器人发了什么"""
    print("\n" + "="*30 + " NEW REQUEST " + "="*30)
    print(f"[Path]: {request.path}")
    print(f"[Method]: {request.method}")
    print(f"[Headers]:\n{request.headers}")
    # 获取原始数据字符串
    raw_data = request.get_data(as_text=True)
    print(f"[Raw Body String]: {raw_data}")
    print("="*73 + "\n")

# --- 中间件：ApiKey 验证 ---
def require_apikey(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        # 1. 先打印日志，不管有没有 Key
        log_request_debug()

        if not MY_API_KEY:
            return f(*args, **kwargs)

        request_key = request.headers.get('ApiKey')
        
        # 调试日志：看看机器人到底发没发 Key
        if request_key != MY_API_KEY:
             print(f"!!! API Key 验证失败. 期望: {MY_API_KEY}, 实际收到: {request_key}")
             return response_json(code=400, msg=f"API Key 无效或缺失. Receive: {request_key}")
        
        return f(*args, **kwargs)
    return decorated

# ================= 接口实现 =================

@app.route('/SearchMusicList', methods=['POST'])
@require_apikey
def search_music_list():
    try:
        # === 核心修改：强力解析 + 详细日志 ===
        print(">>> 正在尝试解析参数...")
        
        # 1. 尝试强制解析 JSON (silent=True 不报错, force=True 无视 Content-Type)
        payload = request.get_json(force=True, silent=True)
        
        # 2. 如果解析失败，尝试回退到 form-data 或 args
        if not payload:
            print(">>> get_json 返回空，尝试读取 request.values (Form/Args)...")
            payload = request.values.to_dict()
        
        print(f">>> 最终解析到的 Payload: {payload} (Type: {type(payload)})")
        
        # 防御性编程：确保 payload 是字典
        if not isinstance(payload, dict):
             payload = {}

        keyword = payload.get('Keyword')
        page = payload.get('Page', 1)
        
        print(f">>> 提取参数: Keyword={keyword}, Page={page}")

        if not keyword:
            return response_json(code=400, msg="参数 Keyword 不能为空 (解析后为 None)")

        limit = 20
        # 确保 page 是 int
        try:
            offset = (int(page) - 1) * limit
        except ValueError:
            offset = 0

        target_url = f"{NETEASE_API_BASE}/cloudsearch"
        print(f">>> 请求网易云接口: {target_url}")
        
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
        else:
             print(f"!!! 网易云返回异常: {n_data}")

        return response_json(data=results)

    except Exception as e:
        # 打印详细的报错堆栈，不仅仅是错误信息
        error_trace = traceback.format_exc()
        print(f"!!! 发生严重错误:\n{error_trace}")
        return response_json(code=500, msg=f"Server Error: {str(e)}")


@app.route('/GetMusicDetail', methods=['GET'])
@require_apikey
def get_music_detail():
    try:
        # GET 请求也要看参数
        print(f">>> GetMusicDetail Params: {request.args}")
        
        song_id = request.args.get('id')
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
            print(f"!!! 解析链接失败: {url_err}")

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
        print(f"!!! GetMusicDetail Error:\n{error_trace}")
        return response_json(code=500, msg=str(e))

@app.route('/SearchMusicRecommendedList', methods=['POST'])
@require_apikey
def search_recommended():
    try:
        print(">>> 进入推荐搜索...")
        # 同样应用强力解析
        payload = request.get_json(force=True, silent=True) or request.values.to_dict() or {}
        print(f">>> 推荐 Payload: {payload}")

        keyword = payload.get('Keyword')
        size = payload.get('size', 10)

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
        print(f"!!! SearchMusicRecommendedList Error:\n{error_trace}")
        return response_json(code=500, msg=str(e))

# if __name__ == '__main__':
#    app.run(debug=True, port=5000)
