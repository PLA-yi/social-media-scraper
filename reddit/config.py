# 全局配置常量

BASE_URL      = "https://www.reddit.com"
OUTPUT_DIR    = "data"      # 数据输出目录（相对于项目根目录）
POST_COUNT    = 20          # 默认采集帖子数量
COMMENT_COUNT = 500         # 每帖最多评论数
REQUEST_PAUSE = 1.5         # 请求间隔（秒），避免触发限流

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
