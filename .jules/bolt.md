## 2026-02-21 - [Optimizing yt-dlp and Bot Concurrency]
**Learning:** Enabling `concurrent_fragment_downloads` in `yt-dlp` significantly speeds up DASH/HLS downloads which are common for YouTube. Offloading blocking I/O (like `yt-dlp` downloads) to `asyncio.to_thread` is essential for maintaining bot responsiveness in an `asyncio` environment.
**Action:** Always check if blocking operations are being called directly in the main event loop and use `to_thread` or `run_in_executor`. Check library-specific speed optimizations like `yt-dlp`'s fragment downloading.
