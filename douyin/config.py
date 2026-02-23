# 全局配置常量

OUTPUT_DIR    = "data"     # 数据输出目录（相对于项目根目录）
VIDEO_COUNT   = 20         # 关键词搜索默认视频数量
COMMENT_COUNT = 500        # 每视频最多评论数
SCROLL_PAUSE  = 2.0        # 滚动间隔（秒），防反爬
LOAD_TIMEOUT  = 30_000     # 页面加载超时（ms）
HEADLESS      = False      # 是否无头模式（False = 显示浏览器）

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
