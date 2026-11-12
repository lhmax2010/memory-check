#!/bin/sh
# GCC / LLVM 镜像内存对比采集脚本（同一块板上分别刷两个镜像，各跑一次或多次）
# TV 镜像开启了 UEP，未签名的脚本文件不能直接用 sh/bash 执行，所以用 bash -c 读入内容运行：
#   bash -c "$(cat /opt/usr/memcheck.sh)" memcheck gcc
#   bash -c "$(cat /opt/usr/memcheck.sh)" memcheck llvm
# 结果目录：/opt/usr/memcheck/<镜像>_boot<序号>_<时间>/
# 脚本自身在后台运行；前台只负责启动并打印查看进度的命令。

SCRIPT=/opt/usr/prelink_ab_stage/memcheck.sh
BASE=/opt/usr/prelink_ab_stage/memcheck
STEADY_MIN_UPTIME=600      # 开机满 10 分钟后才开始判定静止
STEADY_INTERVAL=30         # 每 30 秒采样一次
STEADY_WINDOW=10           # 连续 10 次采样（约 5 分钟）作为判定窗口
STEADY_CPU_BUSY_MAX=21     # 窗口内平均 CPU 忙碌率 < 20%
STEADY_TIMEOUT=1800        # 最多等 45 分钟；超时照常采集，并在结果里标记未静止
GAP_S1_S2=300              # 第一、二次快照间隔 5 分钟（用来看同一次开机内的噪声）
AFTER_DROP_WAIT=120        # 清 page cache 后等 2 分钟再采
ELF_MAX_KB=65536           # 单个 ELF 超过 64MB 不打包，只记录路径
ELF_MIN_FREE_KB=1048576    # 结果分区剩余空间不足 1GB 时不打包 ELF

if [ "$1" = "__bg" ]; then
  MODE=bg; TAG="$2"; OUT="$3"
else
  MODE=fg; TAG="$1"
fi
case "$TAG" in
  gcc|llvm) ;;
  *) echo "用法: bash -c \"\$(cat $SCRIPT)\" memcheck gcc   或   bash -c \"\$(cat $SCRIPT)\" memcheck llvm"; exit 1 ;;
esac

# ---------------- 前台：创建目录、启动后台、打印查看命令 ----------------
if [ "$MODE" = fg ]; then
  [ "$(id -u)" = 0 ] || { echo "需要 root 运行"; exit 1; }
  [ -r "$SCRIPT" ] || { echo "找不到 $SCRIPT，请先 sdb push 到这个位置"; exit 1; }
  mkdir -p "$BASE" || { echo "无法创建 $BASE"; exit 1; }
  N=$(ls -d "$BASE/${TAG}_boot"* 2>/dev/null | wc -l)
  N=$((N + 1))
  OUT="$BASE/${TAG}_boot${N}_$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$OUT" || { echo "无法创建 $OUT"; exit 1; }
  echo RUNNING > "$OUT/STATUS"
  BODY=$(cat "$SCRIPT")
  if command -v setsid >/dev/null 2>&1; then
    setsid nohup bash -c "$BODY" memcheck __bg "$TAG" "$OUT" </dev/null >"$OUT/run.log" 2>&1 &
  else
    nohup bash -c "$BODY" memcheck __bg "$TAG" "$OUT" </dev/null >"$OUT/run.log" 2>&1 &
  fi
  sleep 3
  if [ ! -s "$OUT/run.log" ] || grep -q "NOT signed" "$OUT/run.log"; then
    echo "后台启动失败，run.log 内容如下："; cat "$OUT/run.log"; echo FAILED > "$OUT/STATUS"; exit 1
  fi
  echo "后台采集已启动：$OUT"
  echo "预计 20～60 分钟（含等待系统静止），期间请不要操作电视"
  echo ""
  echo "查看进度：tail -n 20 $OUT/run.log"
  echo "查看状态：cat $OUT/STATUS    （RUNNING=还在跑  DONE=正常结束  FAILED=中途退出）"
  exit 0
fi

# ---------------- 后台：实际采集 ----------------
FINISHED=0
DROP_ORIGINAL=$(cat /proc/sys/vm/drop_caches 2>"$OUT/drop_caches_original.stderr")
ls -l /proc/sys/vm/drop_caches > "$OUT/drop_caches_mode.txt" 2>&1
printf "%s\n" "$DROP_ORIGINAL" > "$OUT/drop_caches_original.txt"
log() { echo "[$(date '+%F %T')] $*"; }
rd() { cat "$1" 2>/dev/null; }

on_exit() {
  if [ -n "$DROP_ORIGINAL" ]; then
    if printf "%s\n" "$DROP_ORIGINAL" > /proc/sys/vm/drop_caches 2>"$OUT/drop_caches_restore.stderr"; then
      cat /proc/sys/vm/drop_caches > "$OUT/drop_caches_restored.txt"
    else log "drop_caches 原值恢复失败"; fi
  fi
  if [ "$FINISHED" = 1 ]; then
    echo DONE > "$OUT/STATUS"
    log "=== 已结束：正常完成（状态 DONE），结果目录 $OUT"
  else
    echo FAILED > "$OUT/STATUS"
    log "=== 已结束：中途退出（状态 FAILED），最后完成的步骤见上方日志"
  fi
}
trap on_exit EXIT
trap 'log "收到终止信号"; exit 1' INT TERM

ps_all() { ps -eo pid,ppid,stat,rss,vsz,etime,comm,args 2>/dev/null || ps aux 2>/dev/null || ps; }

write_columns() {
  cat > "$OUT/COLUMNS.txt" <<'EOF'
各文件列说明（单位 kB）
proc_rollup.txt : 总量(Pss+SwapPss) Pss Pss_Anon Pss_File Pss_Shmem Private_Dirty SwapPss Rss pid 进程名
mapping.txt     : 总量(Pss+SwapPss) Pss SwapPss Private_Dirty Private_Clean Shared_Clean VMA个数 映射名
proc_dso.txt    : 加载的.so个数 VMA个数 可执行文件自身的Private_Dirty 可执行文件自身的Pss ELF类型(02=非PIE 03=PIE) pid 进程名 可执行文件路径
totals.txt      : 全部进程的合计
dso_totals.txt  : 全部进程的 .so 个数、VMA 个数、可执行文件私有脏页合计，以及 PIE / 非 PIE 进程数
05_elf/elf_exec_types.txt : ELF类型 路径（02=非PIE 03=PIE）
EOF
}

pre_info() {
  d="$OUT/00_info"; mkdir -p "$d"
  { echo "tag=$TAG"; date '+%F %T'; echo "uptime: $(rd /proc/uptime)"; } > "$d/run_meta.txt"
  { rd /proc/device-tree/model | tr -d '\000'; echo; uname -a; rd /proc/version; } > "$d/board_kernel.txt"
  rd /proc/cmdline > "$d/cmdline.txt"
  grep -i "system ram" /proc/iomem > "$d/iomem_ram.txt" 2>/dev/null
  for f in /etc/tizen-release /etc/os-release /etc/info.ini /etc/tizen-build.conf; do
    [ -r "$f" ] && { echo "### $f"; cat "$f"; }
  done > "$d/image_release.txt" 2>/dev/null
  if [ -r /proc/config.gz ]; then
    zcat /proc/config.gz > "$d/kernel_config.txt" 2>/dev/null || gzip -dc /proc/config.gz > "$d/kernel_config.txt" 2>/dev/null
  fi
  for f in /proc/sys/vm/*; do
    [ -f "$f" ] && echo "$(basename "$f") = $(rd "$f" | tr '\n' ' ')"
  done > "$d/sysctl_vm.txt"
  for z in /sys/block/zram*; do
    [ -d "$z" ] || continue
    echo "### $z"
    for k in disksize comp_algorithm max_comp_streams mem_limit; do echo "$k: $(rd "$z/$k")"; done
  done > "$d/zram_config.txt"
  rd /proc/swaps > "$d/swaps.txt"
  find /sys/fs/cgroup -maxdepth 4 \( -name memory.max -o -name memory.high -o -name memory.limit_in_bytes -o -name memory.soft_limit_in_bytes \) 2>/dev/null \
    | while read -r f; do echo "$f = $(rd "$f")"; done > "$d/memcg_limits.txt"
  for x in /etc/resourced /usr/etc/resourced /etc/resourced.conf; do
    [ -e "$x" ] && cp -r "$x" "$d/" 2>/dev/null
  done
  rpm -qa --qf '%{NAME} %{VERSION}-%{RELEASE} %{ARCH}\n' 2>/dev/null | sort > "$d/rpm_list.txt"
  ls -la /usr/local /usr/local/lib /usr/local/bin > "$d/usr_local.txt" 2>&1
  ls -la /usr/lib/libc++* /usr/lib/libc++abi* /usr/lib/libstdc++* /usr/lib/libunwind* /usr/lib/libgcc_s* > "$d/cxx_runtime_files.txt" 2>&1
  ps_all > "$d/ps_start.txt"
  df -k > "$d/df.txt" 2>&1
}

cpu_jiffies() { awk '/^cpu /{t=0; for(i=2;i<=NF;i++) t+=$i; print t, $5+$6}' /proc/stat; }

wait_steady() {
  f="$OUT/01_steady_samples.txt"
  echo "# 时间 开机秒数 MemAvailable(kB) Swap已用(kB) CPU忙碌率(%)" > "$f"
  mt=$(awk '/^MemTotal:/{print $2}' /proc/meminfo)
  thr=$((mt / 100))
  log "等待系统静止：开机满 ${STEADY_MIN_UPTIME}s，连续 ${STEADY_WINDOW} 次采样内 MemAvailable 与 Swap 已用的波动都 < ${thr} kB（MemTotal 的 1%），且平均 CPU 忙碌率 < ${STEADY_CPU_BUSY_MAX}%"
  start=$(date +%s)
  set -- $(cpu_jiffies); pt=$1; pi=$2
  STEADY=no
  while :; do
    sleep "$STEADY_INTERVAL"
    set -- $(cpu_jiffies); ct=$1; ci=$2
    dt=$((ct - pt)); di=$((ci - pi)); pt=$ct; pi=$ci
    busy=0; [ "$dt" -gt 0 ] && busy=$(( (dt - di) * 100 / dt ))
    up=$(awk '{print int($1)}' /proc/uptime)
    set -- $(awk '/^MemAvailable:/{a=$2} /^SwapTotal:/{t=$2} /^SwapFree:/{f=$2} END{print a, t-f}' /proc/meminfo)
    echo "$(date +%T) $up $1 $2 $busy" >> "$f"
    el=$(( $(date +%s) - start ))
    ok=$(grep -v '^#' "$f" | tail -n "$STEADY_WINDOW" | awk -v w="$STEADY_WINDOW" -v thr="$thr" -v cb="$STEADY_CPU_BUSY_MAX" -v mu="$STEADY_MIN_UPTIME" -v up="$up" '
      { n++
        if (n==1 || $3<amin) amin=$3; if (n==1 || $3>amax) amax=$3
        if (n==1 || $4<smin) smin=$4; if (n==1 || $4>smax) smax=$4
        b+=$5 }
      END {
        if (up < mu) { printf "no 开机未满 %ds\n", mu; exit }
        if (n < w)   { printf "no 采样数不足 %d/%d\n", n, w; exit }
        r1=amax-amin; r2=smax-smin; ab=b/n
        if (r1>=thr || r2>=thr || ab>cb) { printf "no 窗口波动 MemAvailable=%dkB Swap=%dkB CPU=%.0f%%\n", r1, r2, ab; exit }
        printf "yes 窗口波动 MemAvailable=%dkB Swap=%dkB CPU=%.0f%%\n", r1, r2, ab }')
    case "$ok" in
      yes*) STEADY=yes; log "系统已静止：${ok#yes }"; break ;;
    esac
    if [ "$el" -ge "$STEADY_TIMEOUT" ]; then
      log "等待超时（${el}s），按未静止继续采集：${ok#no }"; break
    fi
    [ $((el % 300)) -lt "$STEADY_INTERVAL" ] && log "仍在等待静止（已等 ${el}s，开机 ${up}s）：${ok#no }"
  done
  echo "steady=$STEADY" >> "$OUT/00_info/run_meta.txt"
}

proc_rollup() {
  d="$1"
  for p in /proc/[0-9]*; do
    [ -r "$p/smaps_rollup" ] || continue
    pid=${p#/proc/}
    c=$(tr -d '\n' < "$p/comm" 2>/dev/null | tr ' ' '_')
    awk -v pid="$pid" -v c="$c" '
      /^Rss:/{rss=$2} /^Pss:/{pss=$2} /^Pss_Anon:/{pa=$2} /^Pss_File:/{pf=$2} /^Pss_Shmem:/{psh=$2}
      /^Private_Dirty:/{pd=$2} /^SwapPss:/{sp=$2}
      END { if (rss>0 || sp>0) printf "%d %d %d %d %d %d %d %d %s %s\n", pss+sp, pss, pa, pf, psh, pd, sp, rss, pid, c }' "$p/smaps_rollup" 2>/dev/null
  done | sort -rn > "$d/proc_rollup.txt"
  awk '{t+=$1; p+=$2; a+=$3; f+=$4; s+=$5; pd+=$6; sp+=$7; n++}
    END { printf "进程数=%d 总量(Pss+SwapPss)=%d Pss=%d Pss_Anon=%d Pss_File=%d Pss_Shmem=%d Private_Dirty=%d SwapPss=%d 匿名合计(Pss_Anon+SwapPss)=%d (kB)\n", n, t, p, a, f, s, pd, sp, a+sp }' \
    "$d/proc_rollup.txt" > "$d/totals.txt"
}

mapping_sum() {
  cat /proc/[0-9]*/smaps 2>/dev/null | awk '
    /^[0-9a-f]+-[0-9a-f]+ /{ n=($6=="" ? "[anon]" : $6); v[n]++; next }
    /^Pss:/{p[n]+=$2} /^SwapPss:/{s[n]+=$2} /^Private_Dirty:/{pd[n]+=$2} /^Private_Clean:/{pc[n]+=$2} /^Shared_Clean:/{sc[n]+=$2}
    END { for (k in v) printf "%d %d %d %d %d %d %d %s\n", p[k]+s[k], p[k], s[k], pd[k], pc[k], sc[k], v[k], k }' \
    | sort -rn > "$1/mapping.txt"
}

proc_dso() {
  d="$1"
  for p in /proc/[0-9]*; do
    pid=${p#/proc/}
    exe=$(readlink "$p/exe" 2>/dev/null); [ -n "$exe" ] || continue
    c=$(tr -d '\n' < "$p/comm" 2>/dev/null | tr ' ' '_')
    et=$(od -An -tx1 -j16 -N1 "$exe" 2>/dev/null | tr -d ' \n'); [ -n "$et" ] || et=NA
    awk -v exe="$exe" -v pid="$pid" -v c="$c" -v et="$et" '
      /^[0-9a-f]+-[0-9a-f]+ /{ n=$6; vm++; cur=(n==exe); if (n ~ /\.so(\.|$)/) so[n]=1; next }
      /^Pss:/{ if (cur) ep+=$2 } /^Private_Dirty:/{ if (cur) ed+=$2 }
      END { k=0; for (x in so) k++; if (vm>0) printf "%d %d %d %d %s %s %s %s\n", k, vm, ed, ep, et, pid, c, exe }' "$p/smaps" 2>/dev/null
  done | sort -rn > "$d/proc_dso.txt"
  awk '{ n++; so+=$1; vm+=$2; ed+=$3; if ($5=="02") e++; else if ($5=="03") pie++ }
    END { printf "进程数=%d .so合计=%d VMA合计=%d 可执行文件私有脏页合计=%dkB 非PIE进程=%d PIE进程=%d\n", n, so, vm, ed, e, pie }' \
    "$d/proc_dso.txt" > "$d/dso_totals.txt"
}

raw_smaps() {
  d="$1"
  if command -v gzip >/dev/null 2>&1; then
    for p in /proc/[0-9]*; do
      echo "### ${p#/proc/} $(tr -d '\n' < "$p/comm" 2>/dev/null) $(readlink "$p/exe" 2>/dev/null)"
      cat "$p/smaps" 2>/dev/null
    done | gzip -c > "$d/smaps_raw.txt.gz"
  else
    for p in /proc/[0-9]*; do
      echo "### ${p#/proc/} $(tr -d '\n' < "$p/comm" 2>/dev/null) $(readlink "$p/exe" 2>/dev/null)"
      cat "$p/smaps" 2>/dev/null
    done > "$d/smaps_raw.txt"
  fi
}

snap() {
  name="$1"; raw="$2"; d="$OUT/$name"; mkdir -p "$d"
  log "快照 $name 开始"
  { date '+%F %T'; echo "uptime: $(rd /proc/uptime)"; } > "$d/time.txt"
  rd /proc/meminfo     > "$d/meminfo.txt"
  rd /proc/vmstat      > "$d/vmstat.txt"
  rd /proc/vmallocinfo > "$d/vmallocinfo.txt"
  rd /proc/buddyinfo   > "$d/buddyinfo.txt"
  rd /proc/pagetypeinfo > "$d/pagetypeinfo.txt"
  rd /proc/slabinfo    > "$d/slabinfo.txt"
  rd /proc/zoneinfo    > "$d/zoneinfo.txt"
  rd /proc/swaps       > "$d/swaps.txt"
  for x in memory cpu io; do echo "### $x"; rd "/proc/pressure/$x"; done > "$d/psi.txt"
  for z in /sys/block/zram*; do [ -d "$z" ] && echo "$z mm_stat: $(rd "$z/mm_stat")"; done > "$d/zram_mm_stat.txt"
  for g in /sys/kernel/debug/mali0/gpu_memory /sys/kernel/debug/gpu/gpu_memory /sys/kernel/debug/dma_buf/bufinfo /sys/kernel/debug/dri/ndp-drm/gem_info; do
    [ -r "$g" ] && { echo "### $g"; cat "$g"; }
  done > "$d/gpu_dmabuf.txt" 2>/dev/null
  ps_all > "$d/ps.txt"
  # 与 TPMS 同一时刻采一份 memps -v，用来对齐 TPMS 的 PSS 口径和 smaps 的 Pss / SwapPss
  { date -Ins; cat /proc/uptime; } > "$d/memps_before.txt"
  if command -v memps >/dev/null 2>&1; then
    memps -v > "$d/memps_v.txt" 2>&1
  else
    echo "memps absent; native vd_memps is supplementary, not a substitute for TPMS memps" > "$d/memps_unavailable.txt"
    if command -v vd_memps >/dev/null 2>&1; then vd_memps -v > "$d/vd_memps_v.txt" 2>&1; fi
  fi
  { date -Ins; cat /proc/uptime; } > "$d/memps_after.txt"
  proc_rollup "$d"
  mapping_sum "$d"
  proc_dso "$d"
  [ "$raw" = raw ] && raw_smaps "$d"
  { date -Ins; cat /proc/uptime; } > "$d/smaps_after.txt"
  log "快照 $name 完成：$(cat "$d/totals.txt")"
  log "快照 $name 进程/库统计：$(cat "$d/dso_totals.txt")"
}

elf_scan() {
  d="$OUT/05_elf"; mkdir -p "$d"
  for dd in /usr/bin /usr/sbin /bin /sbin /usr/libexec /usr/apps/*/bin /opt/usr/apps/*/bin; do
    [ -d "$dd" ] && [ ! -L "$dd" ] || continue
    for f in "$dd"/*; do
      [ -f "$f" ] && [ ! -L "$f" ] || continue
      m=$(od -An -tx1 -N4 "$f" 2>/dev/null | tr -d ' \n')
      [ "$m" = 7f454c46 ] || continue
      echo "$(od -An -tx1 -j16 -N1 "$f" | tr -d ' \n') $f"
    done
  done > "$d/elf_exec_types.txt"
  awk '{ c[$1]++ } END { for (k in c) printf "类型%s %d 个\n", k, c[k] }' "$d/elf_exec_types.txt" > "$d/elf_exec_types_summary.txt"
  log "可执行文件 ELF 类型统计（02=非PIE 03=PIE）：$(tr '\n' ' ' < "$d/elf_exec_types_summary.txt")"
}

elf_collect() {
  d="$OUT/05_elf"; mkdir -p "$d"
  list="$d/collect_list.txt"; skipped="$d/collect_skipped.txt"
  : > "$list"; : > "$skipped"
  { awk '$NF ~ /^\// { print $NF }' "$OUT/02_steady/mapping.txt" | head -n 120
    awk '{ print $NF }' "$OUT/02_steady/proc_dso.txt"; } | sort -u | while read -r f; do
    [ -f "$f" ] || continue
    m=$(od -An -tx1 -N4 "$f" 2>/dev/null | tr -d ' \n')
    [ "$m" = 7f454c46 ] || continue
    sz=$(du -k "$f" 2>/dev/null | awk '{print $1}')
    if [ -n "$sz" ] && [ "$sz" -gt "$ELF_MAX_KB" ]; then
      echo "$sz kB $f" >> "$skipped"
    else
      echo "$f" >> "$list"
    fi
  done
  free=$(df -k "$BASE" 2>/dev/null | awk 'END { print $(NF-2) }')
  if [ -z "$free" ] || [ "$free" -lt "$ELF_MIN_FREE_KB" ]; then
    log "结果分区剩余空间 ${free:-未知} kB，不足 1GB，跳过 ELF 打包（文件清单已保存在 $list）"
    return 0
  fi
  if tar czf "$d/elf_files.tar.gz" $(cat "$list") 2>"$d/tar_err.txt"; then
    log "ELF 打包完成：$(wc -l < "$list") 个文件，$(du -k "$d/elf_files.tar.gz" | awk '{print $1}') kB；超过 64MB 未打包的见 $skipped"
  else
    log "ELF 打包有报错，见 $d/tar_err.txt（已打进去的部分仍在 elf_files.tar.gz）"
  fi
}

# ---------------- 主流程 ----------------
log "=== 开始：镜像=$TAG 结果目录=$OUT"
write_columns
log "步骤 1/6 记录板子、内核、镜像和内存相关配置"
pre_info
log "步骤 2/6 等待系统静止"
wait_steady
log "步骤 3/6 静止后快照（含全部进程 smaps 原始数据）"
snap 02_steady raw
log "步骤 4/6 等待 ${GAP_S1_S2}s 后再采一次，用来看噪声"
sleep "$GAP_S1_S2"
snap 03_steady_repeat raw
log "步骤 5/6 清 page cache（sync + drop_caches=3），等待 ${AFTER_DROP_WAIT}s 后快照"
sync
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || log "drop_caches 写入失败"
sleep "$AFTER_DROP_WAIT"
snap 04_after_drop_caches raw
log "步骤 6/6 统计可执行文件 PIE 情况，并打包关键 ELF 供宿主机分析"
elf_scan
elf_collect
log "结果目录大小：$(du -sk "$OUT" | awk '{print $1}') kB"
FINISHED=1
exit 0
