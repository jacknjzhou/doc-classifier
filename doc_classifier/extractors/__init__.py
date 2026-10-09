"""抽取器子包。

导入本包即完成全部内置抽取器/检测器的注册（rule/llm/material），
保证 pipeline 单独运行时 `get_extractor` 可用（不依赖测试文件的导入副作用）。
新增内置抽取器模块后，在此追加一行导入即可。
"""

from . import llm, material, rule  # noqa: F401  触发模块级 register_* 注册
