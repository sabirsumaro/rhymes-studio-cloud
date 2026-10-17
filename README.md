# Rhymes Studio Cloud

A separate GitHub Actions project for generating original English nursery-rhyme videos and delivering them to Telegram. It does not modify `sabirsumaroai/rhymes-bot`.

## Honest scope
This is a starter pipeline, not a promise of studio-quality 3D animation or natural singing. It generates original English lyrics, narration, a simple animated 2D scene video, a thumbnail and metadata. The default voice is neural text-to-speech, not singing. Upgrade the animation/audio engine only after reviewing the first test output.

## Setup
1. Create a **new, separate** GitHub repository named `rhymes-studio-cloud`.
2. Upload the contents of this folder, including `.github/workflows/daily.yml`.
3. In Settings → Secrets and variables → Actions, add:
   - `GEMINI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. In Settings → Actions → General, allow GitHub Actions to run.
5. Open Actions → `Daily Rhymes Studio` → Run workflow. First run manually with `dry_run=true` to test the workflow without Telegram delivery, then run with `dry_run=false`.
6. Scheduled runs use UTC. The included schedule is 02:30 UTC (08:00 IST).

## Important
- GitHub-hosted runners have limited free usage; no unlimited or failure-proof claim is made.
- Never commit API keys or bot tokens.
- Do not use copyrighted lyrics, melodies, characters, or footage. Review every generated video before publishing.
- Set the YouTube audience setting accurately; nursery-rhyme content directed to children will generally need to be marked Made for Kids.
- Generated narration is not sung vocals. For actual musical singing, a genuinely free and permitted singing-generation system would need to be separately evaluated; do not assume a free AI API is unlimited.
