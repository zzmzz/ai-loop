# 贡献指南

感谢你对 AI Loop 的兴趣！

完整的开发指南（环境搭建、测试规范、模块改动注意事项、发版流程）请参阅：

**[docs/development.md](docs/development.md)**

## 快速开始

```bash
git clone https://github.com/zmzhu/ai-loop.git
cd ai-loop
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## 提交规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：`feat:` / `fix:` / `docs:` / `refactor:` / `test:` / `chore:`

## 项目文档

所有技术文档按业务域组织在 `docs/` 目录下，入口索引：**[docs/index.md](docs/index.md)**
