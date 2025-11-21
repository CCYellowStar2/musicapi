from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import functools

app = Flask(__name__)
# 开启跨域支持 (文档中提到建议支持 CORS)
CORS(app)

# ================= 配置区域 =================
# 1. 你的网易云 API 地址 (已修改为你提供的 Vercel 地址)
NETEASE_API_BASE = "https://music.ccyacg.xyz"

# 2. 你的 API Key (对应文档中的 ApiKey)
MY_API_KEY = "1234567890" 
# ===========================================

# --- 统一响应格式 ---
def response_json(data=None, code=200, msg="操作成功"):
    return jsonify({
        "code": code,
        "message": msg, 
        "data": data
    })

# --- 中间件：ApiKey 验证 ---
def require_apikey(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        request_key = request.headers.get('ApiKey')
        # 如果配置了 Key 且请求没带，或者不对
        if MY_API_KEY and request_key != MY_API_KEY:
             return response_json(code=400, msg="API Key 无效或缺失")
        return f(*args, **kwargs)
    return decorated

# ================= 接口实现 =================

# 1. 搜索接口 (POST) /SearchMusicList
@app.route('/SearchMusicList', methods=['POST'])
@require_apikey
def search_music_list():
    try:
        payload = request.json or {}
        keyword = payload.get('Keyword')
        page = payload.get('Page', 1)
        
        if not keyword:
            return response_json(code=400, msg="参数 Keyword 不能为空")

        limit = 20
        offset = (int(page) - 1) * limit

        # 调用你的网易云 Vercel 服务
        target_url = f"{NETEASE_API_BASE}/cloudsearch"
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
        return response_json(code=500, msg=f"Server Error: {str(e)}")


# 2. 获取详情接口 (GET) /GetMusicDetail
@app.route('/GetMusicDetail', methods=['GET'])
@require_apikey
def get_music_detail():
    try:
        song_id = request.args.get('id')
        if not song_id:
            return response_json(code=400, msg="参数 id 不能为空")

        # A: 获取播放链接
        url_api = f"{NETEASE_API_BASE}/song/url/v1"
        # 尝试 standard, exhigh, lossless, hires
        url_resp = requests.get(url_api, params={"id": song_id, "level": "exhigh"})
        url_data = url_resp.json()
        
        music_url = ""
        if url_data.get('code') == 200 and url_data.get('data'):
            music_url = url_data['data'][0].get('url')

        # B: 获取歌词
        lrc_api = f"{NETEASE_API_BASE}/lyric"
        lrc_resp = requests.get(lrc_api, params={"id": song_id})
        lrc_data = lrc_resp.json()
        
        lyric_text = ""
        if lrc_data.get('code') == 200:
            lyric_text = lrc_data.get('lrc', {}).get('lyric', "")

        if not music_url:
             return response_json(code=400, msg="无法获取播放链接(可能需要VIP)")

        return response_json(data={
            "url": music_url,
            "lyric": lyric_text,
            "id": song_id
        })

    except Exception as e:
        return response_json(code=500, msg=str(e))


# 3. 推荐搜索接口 (POST) /SearchMusicRecommendedList
@app.route('/SearchMusicRecommendedList', methods=['POST'])
@require_apikey
def search_recommended():
    try:
        payload = request.json or {}
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
        return response_json(code=500, msg=str(e))

# Vercel 需要这个 app 对象，但不需要 app.run()
# if __name__ == '__main__':
#    app.run()
