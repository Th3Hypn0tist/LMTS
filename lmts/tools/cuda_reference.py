from __future__ import annotations

import ctypes
import ctypes.util
import os
import statistics
from dataclasses import dataclass
from typing import Any


class CudaUnavailable(RuntimeError):
    pass


_CUresult = ctypes.c_int
_CUdevice = ctypes.c_int
_CUdeviceptr = ctypes.c_uint64
_CUcontext = ctypes.c_void_p
_CUevent = ctypes.c_void_p
_CUstream = ctypes.c_void_p
_CUmodule = ctypes.c_void_p
_CUfunction = ctypes.c_void_p


class _CUuuid(ctypes.Structure):
    _fields_ = [("bytes", ctypes.c_ubyte * 16)]


@dataclass(frozen=True, slots=True)
class CudaDeviceIdentity:
    index: int
    name: str
    uuid: str | None
    total_memory_bytes: int | None

    def target(self) -> dict[str, object]:
        return {
            "device_index": self.index,
            "vendor": "NVIDIA",
            "model": self.name,
            "uuid": self.uuid,
        }


class CudaDriver:
    def __init__(self) -> None:
        names = [ctypes.util.find_library("cuda"), "libcuda.so.1", "nvcuda.dll"]
        self.lib = None
        loader = ctypes.WinDLL if os.name == "nt" else ctypes.CDLL
        for name in names:
            if not name:
                continue
            try:
                self.lib = loader(name)
                break
            except OSError:
                continue
        if self.lib is None:
            raise CudaUnavailable("CUDA driver library not available")
        self._bind()
        self._check(self.cuInit(0), "cuInit")

    def _function(self, *names: str):
        for name in names:
            fn = getattr(self.lib, name, None)
            if fn is not None:
                fn.restype = _CUresult
                return fn
        raise CudaUnavailable(f"CUDA driver symbol unavailable: {names[0]}")

    @staticmethod
    def _args(function, *types) -> None:
        function.argtypes = list(types)

    def _bind(self) -> None:
        self.cuInit = self._function("cuInit")
        self._args(self.cuInit, ctypes.c_uint)

        self.cuDeviceGetCount = self._function("cuDeviceGetCount")
        self._args(self.cuDeviceGetCount, ctypes.POINTER(ctypes.c_int))
        self.cuDeviceGet = self._function("cuDeviceGet")
        self._args(self.cuDeviceGet, ctypes.POINTER(_CUdevice), ctypes.c_int)
        self.cuDeviceGetName = self._function("cuDeviceGetName")
        self._args(self.cuDeviceGetName, ctypes.c_char_p, ctypes.c_int, _CUdevice)
        self.cuDeviceTotalMem = self._function("cuDeviceTotalMem_v2", "cuDeviceTotalMem")
        self._args(self.cuDeviceTotalMem, ctypes.POINTER(ctypes.c_size_t), _CUdevice)
        self.cuDeviceGetUuid = getattr(self.lib, "cuDeviceGetUuid_v2", None) or getattr(self.lib, "cuDeviceGetUuid", None)
        if self.cuDeviceGetUuid is not None:
            self.cuDeviceGetUuid.restype = _CUresult
            self._args(self.cuDeviceGetUuid, ctypes.POINTER(_CUuuid), _CUdevice)

        self.cuCtxCreate = self._function("cuCtxCreate_v2", "cuCtxCreate")
        self._args(self.cuCtxCreate, ctypes.POINTER(_CUcontext), ctypes.c_uint, _CUdevice)
        self.cuCtxDestroy = self._function("cuCtxDestroy_v2", "cuCtxDestroy")
        self._args(self.cuCtxDestroy, _CUcontext)
        self.cuCtxSynchronize = self._function("cuCtxSynchronize")
        self._args(self.cuCtxSynchronize)

        self.cuMemAlloc = self._function("cuMemAlloc_v2", "cuMemAlloc")
        self._args(self.cuMemAlloc, ctypes.POINTER(_CUdeviceptr), ctypes.c_size_t)
        self.cuMemFree = self._function("cuMemFree_v2", "cuMemFree")
        self._args(self.cuMemFree, _CUdeviceptr)
        self.cuMemHostAlloc = self._function("cuMemHostAlloc")
        self._args(self.cuMemHostAlloc, ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t, ctypes.c_uint)
        self.cuMemFreeHost = self._function("cuMemFreeHost")
        self._args(self.cuMemFreeHost, ctypes.c_void_p)
        self.cuMemcpyHtoD = self._function("cuMemcpyHtoD_v2", "cuMemcpyHtoD")
        self._args(self.cuMemcpyHtoD, _CUdeviceptr, ctypes.c_void_p, ctypes.c_size_t)
        self.cuMemcpyDtoH = self._function("cuMemcpyDtoH_v2", "cuMemcpyDtoH")
        self._args(self.cuMemcpyDtoH, ctypes.c_void_p, _CUdeviceptr, ctypes.c_size_t)
        self.cuMemcpyDtoD = self._function("cuMemcpyDtoD_v2", "cuMemcpyDtoD")
        self._args(self.cuMemcpyDtoD, _CUdeviceptr, _CUdeviceptr, ctypes.c_size_t)

        self.cuEventCreate = self._function("cuEventCreate")
        self._args(self.cuEventCreate, ctypes.POINTER(_CUevent), ctypes.c_uint)
        self.cuEventRecord = self._function("cuEventRecord")
        self._args(self.cuEventRecord, _CUevent, _CUstream)
        self.cuEventSynchronize = self._function("cuEventSynchronize")
        self._args(self.cuEventSynchronize, _CUevent)
        self.cuEventElapsedTime = self._function("cuEventElapsedTime")
        self._args(self.cuEventElapsedTime, ctypes.POINTER(ctypes.c_float), _CUevent, _CUevent)
        self.cuEventDestroy = self._function("cuEventDestroy_v2", "cuEventDestroy")
        self._args(self.cuEventDestroy, _CUevent)

        self.cuModuleLoadData = self._function("cuModuleLoadData")
        self._args(self.cuModuleLoadData, ctypes.POINTER(_CUmodule), ctypes.c_void_p)
        self.cuModuleUnload = self._function("cuModuleUnload")
        self._args(self.cuModuleUnload, _CUmodule)
        self.cuModuleGetFunction = self._function("cuModuleGetFunction")
        self._args(self.cuModuleGetFunction, ctypes.POINTER(_CUfunction), _CUmodule, ctypes.c_char_p)
        self.cuLaunchKernel = self._function("cuLaunchKernel")
        self._args(
            self.cuLaunchKernel,
            _CUfunction,
            ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
            ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
            ctypes.c_uint,
            _CUstream,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
        )

    @staticmethod
    def _check(code: int, operation: str) -> None:
        if int(code) != 0:
            raise CudaUnavailable(f"{operation} failed with CUDA error {int(code)}")

    def device_count(self) -> int:
        count = ctypes.c_int()
        self._check(self.cuDeviceGetCount(ctypes.byref(count)), "cuDeviceGetCount")
        return count.value

    def device(self, index: int) -> int:
        device = _CUdevice()
        self._check(self.cuDeviceGet(ctypes.byref(device), index), "cuDeviceGet")
        return device.value

    def identity(self, index: int) -> CudaDeviceIdentity:
        device = self.device(index)
        name = ctypes.create_string_buffer(256)
        self._check(self.cuDeviceGetName(name, len(name), device), "cuDeviceGetName")
        total = ctypes.c_size_t()
        self._check(self.cuDeviceTotalMem(ctypes.byref(total), device), "cuDeviceTotalMem")
        uuid_text = None
        if self.cuDeviceGetUuid is not None:
            uuid_value = _CUuuid()
            if int(self.cuDeviceGetUuid(ctypes.byref(uuid_value), device)) == 0:
                uuid_text = bytes(uuid_value.bytes).hex()
        return CudaDeviceIdentity(index, name.value.decode("utf-8", errors="replace"), uuid_text, total.value)

    def context(self, index: int) -> _CUcontext:
        ctx = _CUcontext()
        self._check(self.cuCtxCreate(ctypes.byref(ctx), 0, self.device(index)), "cuCtxCreate")
        return ctx

    def timed(self, operation, repeats: int = 1) -> list[float]:
        samples: list[float] = []
        for _ in range(repeats):
            start = _CUevent()
            end = _CUevent()
            self._check(self.cuEventCreate(ctypes.byref(start), 0), "cuEventCreate")
            self._check(self.cuEventCreate(ctypes.byref(end), 0), "cuEventCreate")
            try:
                self._check(self.cuEventRecord(start, None), "cuEventRecord")
                operation()
                self._check(self.cuEventRecord(end, None), "cuEventRecord")
                self._check(self.cuEventSynchronize(end), "cuEventSynchronize")
                elapsed = ctypes.c_float()
                self._check(self.cuEventElapsedTime(ctypes.byref(elapsed), start, end), "cuEventElapsedTime")
                samples.append(float(elapsed.value) / 1000.0)
            finally:
                self.cuEventDestroy(start)
                self.cuEventDestroy(end)
        return samples


def _throughput(samples: list[float], bytes_per_sample: int) -> dict[str, object]:
    median = statistics.median(samples)
    rate = bytes_per_sample / median if median > 0 else 0.0
    return {
        "sample_count": len(samples),
        "sample_seconds": samples,
        "median_seconds": median,
        "bytes_per_sample": bytes_per_sample,
        "throughput_bytes_per_second": rate,
        "throughput_gib_per_second": rate / (1024 ** 3),
    }


def transfer_benchmarks(driver: CudaDriver, index: int, *, buffer_bytes: int = 64 * 1024 * 1024, repeats_per_sample: int = 8, sample_count: int = 5) -> list[dict[str, Any]]:
    identity = driver.identity(index)
    target = identity.target()
    ctx = driver.context(index)
    src = _CUdeviceptr()
    dst = _CUdeviceptr()
    host = ctypes.c_void_p()
    try:
        driver._check(driver.cuMemAlloc(ctypes.byref(src), buffer_bytes), "cuMemAlloc")
        driver._check(driver.cuMemAlloc(ctypes.byref(dst), buffer_bytes), "cuMemAlloc")
        driver._check(driver.cuMemHostAlloc(ctypes.byref(host), buffer_bytes, 0), "cuMemHostAlloc")
        ctypes.memset(host, 0xA5, buffer_bytes)
        driver._check(driver.cuMemcpyHtoD(src, host, buffer_bytes), "cuMemcpyHtoD")

        def d2d() -> None:
            for _ in range(repeats_per_sample):
                driver._check(driver.cuMemcpyDtoD(dst, src, buffer_bytes), "cuMemcpyDtoD")

        def h2d() -> None:
            for _ in range(repeats_per_sample):
                driver._check(driver.cuMemcpyHtoD(dst, host, buffer_bytes), "cuMemcpyHtoD")

        def d2h() -> None:
            for _ in range(repeats_per_sample):
                driver._check(driver.cuMemcpyDtoH(host, src, buffer_bytes), "cuMemcpyDtoH")

        tests = []
        for benchmark_id, label, method, op in (
            ("lmts.reference.gpu.d2d", "Device to device copy", "cuda_memcpy_d2d", d2d),
            ("lmts.reference.gpu.h2d_pinned", "Pinned host to device copy", "cuda_memcpy_h2d", h2d),
            ("lmts.reference.gpu.d2h_pinned", "Device to pinned host copy", "cuda_memcpy_d2h", d2h),
        ):
            op()
            samples = driver.timed(op, sample_count)
            tests.append({
                "benchmark_id": benchmark_id,
                "label": label,
                "method": method,
                "method_version": 1,
                "status": "completed",
                "target": target,
                "metrics": {
                    **_throughput(samples, buffer_bytes * repeats_per_sample),
                    "buffer_bytes": buffer_bytes,
                    "repeats_per_sample": repeats_per_sample,
                    "host_memory": "pinned" if "pinned" in benchmark_id else None,
                },
            })
        return tests
    finally:
        if host.value:
            driver.cuMemFreeHost(host)
        if dst.value:
            driver.cuMemFree(dst)
        if src.value:
            driver.cuMemFree(src)
        driver.cuCtxDestroy(ctx)


_PTX = r'''
.version 6.0
.target sm_52
.address_size 64

.visible .entry lmts_fma(
    .param .u64 data,
    .param .u32 iterations
)
{
    .reg .pred %p;
    .reg .b32 %r<5>;
    .reg .b64 %rd<5>;
    .reg .f32 %f<4>;

    ld.param.u64 %rd1, [data];
    ld.param.u32 %r1, [iterations];
    mov.u32 %r2, %tid.x;
    mov.u32 %r3, %ctaid.x;
    mov.u32 %r4, %ntid.x;
    mad.lo.s32 %r2, %r3, %r4, %r2;
    mul.wide.u32 %rd2, %r2, 4;
    add.s64 %rd3, %rd1, %rd2;
    ld.global.f32 %f1, [%rd3];
    mov.f32 %f2, 1.000001;
    mov.f32 %f3, 0.000001;
    mov.u32 %r2, 0;
LOOP:
    fma.rn.f32 %f1, %f1, %f2, %f3;
    add.u32 %r2, %r2, 1;
    setp.lt.u32 %p, %r2, %r1;
    @%p bra LOOP;
    st.global.f32 [%rd3], %f1;
    ret;
}
'''


def compute_benchmark(driver: CudaDriver, index: int, *, blocks: int = 4096, threads: int = 256, iterations: int = 4096, sample_count: int = 5) -> dict[str, Any]:
    identity = driver.identity(index)
    ctx = driver.context(index)
    data = _CUdeviceptr()
    module = _CUmodule()
    function = _CUfunction()
    element_count = blocks * threads
    size = element_count * 4
    try:
        driver._check(driver.cuMemAlloc(ctypes.byref(data), size), "cuMemAlloc")
        ptx = ctypes.create_string_buffer(_PTX.encode("ascii"))
        driver._check(driver.cuModuleLoadData(ctypes.byref(module), ctypes.cast(ptx, ctypes.c_void_p)), "cuModuleLoadData")
        driver._check(driver.cuModuleGetFunction(ctypes.byref(function), module, b"lmts_fma"), "cuModuleGetFunction")
        iterations_arg = ctypes.c_uint(iterations)
        data_arg = _CUdeviceptr(data.value)
        args = (ctypes.c_void_p * 2)(
            ctypes.cast(ctypes.byref(data_arg), ctypes.c_void_p),
            ctypes.cast(ctypes.byref(iterations_arg), ctypes.c_void_p),
        )

        def launch() -> None:
            driver._check(driver.cuLaunchKernel(function, blocks, 1, 1, threads, 1, 1, 0, None, args, None), "cuLaunchKernel")

        launch()
        driver._check(driver.cuCtxSynchronize(), "cuCtxSynchronize")
        samples = driver.timed(launch, sample_count)
        median = statistics.median(samples)
        operations = element_count * iterations * 2
        return {
            "benchmark_id": "lmts.reference.gpu.fma_fp32",
            "label": "FP32 FMA kernel",
            "method": "cuda_ptx_fma_fp32",
            "method_version": 1,
            "status": "completed",
            "target": identity.target(),
            "metrics": {
                "sample_count": len(samples),
                "sample_seconds": samples,
                "median_seconds": median,
                "blocks": blocks,
                "threads_per_block": threads,
                "iterations_per_thread": iterations,
                "operations_per_sample": operations,
                "operations_per_second": operations / median if median > 0 else 0.0,
                "gigaoperations_per_second": operations / median / 1_000_000_000 if median > 0 else 0.0,
            },
        }
    finally:
        if module.value:
            driver.cuModuleUnload(module)
        if data.value:
            driver.cuMemFree(data)
        driver.cuCtxDestroy(ctx)


def run_cuda_reference() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    driver = CudaDriver()
    count = driver.device_count()
    if count < 1:
        raise CudaUnavailable("CUDA driver reports no devices")
    tests: list[dict[str, Any]] = []
    devices: list[dict[str, Any]] = []
    for index in range(count):
        identity = driver.identity(index)
        devices.append({**identity.target(), "total_memory_bytes": identity.total_memory_bytes})
        tests.extend(transfer_benchmarks(driver, index))
        tests.append(compute_benchmark(driver, index))
    return tests, {"devices": devices, "backend": "cuda_driver_api"}
