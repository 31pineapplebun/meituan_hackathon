"""轻量级内存任务存储 + 后台线程执行器。

评测是耗时任务(完整模式要几分钟),所以 POST /api/evaluate 立刻返回 job_id,真正的
评测在后台线程里跑;前端轮询 GET /api/jobs/{id} 看进度,完成后再取报告。

注: 内存存储,进程重启即丢 —— 学习项目够用;生产可换 Redis / 专用任务队列(Celery / RQ)。
为避免长跑进程无限堆积,这里对任务数设了上限(淘汰最老的已结束任务)。
"""
import threading
import uuid

MAX_JOBS = 50  # 最多保留的任务数;超出则淘汰最老的「已结束」任务,防止内存无限增长

_jobs = {}
_lock = threading.Lock()


def _evict_locked():
    """已持锁。超出上限时按插入顺序淘汰最老的「已结束」任务(不动正在跑的)。"""
    while len(_jobs) > MAX_JOBS:
        for jid, job in _jobs.items():  # dict 保持插入顺序,最老的在前
            if job["status"] != "running":
                del _jobs[jid]
                break
        else:
            break  # 全在跑,无可淘汰


def create_job():
    """登记一个新任务,返回 job_id。"""
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": "running",   # running | done | failed
            "progress": {"current": 0, "total": 0, "msg": "已提交,准备中…"},
            "report": None,
            "error": None,
        }
        _evict_locked()
    return job_id


def get_job(job_id):
    """取任务快照。

    progress 是会被后台线程持续更新的嵌套 dict,所以单独拷一层,让调用方拿到稳定快照
    (report 只在完成时设置一次、之后不再原地改,浅引用即可)。
    """
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        return {**job, "progress": dict(job["progress"])}


def _set_progress(job_id, current, total, msg):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id]["progress"] = {"current": current, "total": total, "msg": msg}


def start_job(job_id, work):
    """在后台守护线程里执行 work(progress_cb) -> report dict。

    work 返回的 dict 若含 "error" 字段视为失败;抛异常也视为失败。
    """
    def runner():
        try:
            report = work(lambda c, t, m: _set_progress(job_id, c, t, m))
            with _lock:
                if job_id not in _jobs:
                    return
                if isinstance(report, dict) and report.get("error"):
                    _jobs[job_id]["status"] = "failed"
                    _jobs[job_id]["error"] = report["error"]
                else:
                    _jobs[job_id]["status"] = "done"
                    _jobs[job_id]["report"] = report
                    # 整体替换 progress(而非原地改 msg),避免动到读取方已持有的同一个 dict
                    _jobs[job_id]["progress"] = {**_jobs[job_id]["progress"], "msg": "完成"}
        except Exception as e:  # noqa: BLE001 — 任何引擎异常都转成失败态回传前端,而不是 500
            with _lock:
                if job_id in _jobs:
                    _jobs[job_id]["status"] = "failed"
                    _jobs[job_id]["error"] = f"{type(e).__name__}: {e}"

    threading.Thread(target=runner, daemon=True).start()
