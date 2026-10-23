# Public test fixtures / 公开测试夹具

`ui-upload.flac` and `ui-preview.mp3` are generated silence, not song recordings. Run `python scripts/generate_test_fixtures.py` to create deterministic synthetic note fixtures for tests. `Setup.cmd` includes this step. Existing fixtures are never overwritten.

公开仓库只包含人工生成的静音测试音频。运行 `python scripts/generate_test_fixtures.py` 生成可复现的合成音符夹具，完整安装已包含这一步。脚本不会覆盖已有文件。

Local private listening analysis may use historical fixture filenames. Those JSON files are ignored by Git and are not published. Public synthetic data checks software invariants, not melody recognition accuracy or musical quality.

本地人工试听可能沿用历史夹具文件名，相应 JSON 不发布。合成数据用于检查软件约束，不用来宣称识别准确率或伴奏质量。
