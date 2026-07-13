"""外部 MCP client 注入能力。

该包让 HPC Agent 可以作为 MCP Client 连接第三方 MCP Server，
发现被白名单允许的外部 tools，并以 external_<server>_<tool> 的形式
注入到自己的工具系统中。
"""

