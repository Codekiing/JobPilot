# JobPilot Web Demo

JobPilot 的本地前端工作台，集中展示用户画像进度、岗位匹配结果、待确认岗位和求职流程。

页面不内置或伪造推荐岗位。首次打开时岗位列表为空。用户上传简历后，页面只解析并填充画像；用户补全画像并点击“确认保存并搜索岗位”后，才连接项目根目录的本地 API 动态搜索并展示本次真实采集到的职位。官网动态页面、官网 API、逐家大厂检索、牛客、OfferShow、实习僧和 BOSS 会分别显示实际状态与岗位数，官网入口可访问但没有解析出具体职位时也会明确列为覆盖缺口。

## 本地运行

```bash
npm install
npm run dev
```

打开 `http://localhost:3000`。岗位搜索、简历解析和画像匹配通过项目根目录的 `/jobpilot/*` 本地 API 执行。

需要从局域网设备验收时，可用 `NEXT_PUBLIC_JOBPILOT_API_URL` 指向同一台机器的 API；API 端通过 `JOBPILOT_ALLOWED_BROWSER_ORIGINS` 显式增加对应前端来源。默认仍只允许 localhost 与已发布站点。

## 验证

```bash
npm run build
```
