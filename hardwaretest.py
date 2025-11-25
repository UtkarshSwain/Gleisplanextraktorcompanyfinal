"""

Hardware Detection and Configuration Test

Run this to check your system capabilities and get recommended settings.

"""



import platform

import psutil

import sys



def print_hardware_info():

    """Print detailed hardware configuration for debugging."""

    print("\n" + "="*70)

    print("HARDWARE CONFIGURATION")

    print("="*70)

   

    # System info

    print(f"\n📱 System: {platform.system()} {platform.release()}")

    print(f"   Machine: {platform.machine()}")

    print(f"   Processor: {platform.processor()}")

    print(f"   Python Version: {sys.version.split()[0]}")

   

    # CPU info

    cpu_count_physical = psutil.cpu_count(logical=False)

    cpu_count_logical = psutil.cpu_count(logical=True)

    print(f"\n🖥️  CPU:")

    print(f"   Physical cores: {cpu_count_physical}")

    print(f"   Logical cores: {cpu_count_logical}")

    try:

        cpu_freq = psutil.cpu_freq()

        if cpu_freq:

            print(f"   Current Frequency: {cpu_freq.current:.2f} MHz")

            print(f"   Max Frequency: {cpu_freq.max:.2f} MHz")

    except:

        print(f"   Frequency: Not available")

   

    # CPU usage

    cpu_percent = psutil.cpu_percent(interval=1)

    print(f"   Current Usage: {cpu_percent}%")

   

    # RAM info

    ram = psutil.virtual_memory()

    print(f"\n💾 RAM:")

    print(f"   Total: {ram.total / (1024**3):.2f} GB")

    print(f"   Available: {ram.available / (1024**3):.2f} GB")

    print(f"   Used: {ram.used / (1024**3):.2f} GB ({ram.percent}%)")

   

    # GPU info (CUDA/PyTorch)

    print(f"\n🎮 GPU (PyTorch/CUDA):")

    try:

        import torch

        print(f"   PyTorch Version: {torch.__version__}")

        if torch.cuda.is_available():

            print(f"   ✅ CUDA Available: YES")

            print(f"   CUDA Version: {torch.version.cuda}")

            print(f"   GPU Count: {torch.cuda.device_count()}")

            for i in range(torch.cuda.device_count()):

                print(f"\n   GPU {i}:")

                print(f"      Name: {torch.cuda.get_device_name(i)}")

                props = torch.cuda.get_device_properties(i)

                print(f"      Total Memory: {props.total_memory / (1024**3):.2f} GB")

                print(f"      Compute Capability: {props.major}.{props.minor}")

                # Check memory usage

                try:

                    mem_allocated = torch.cuda.memory_allocated(i) / (1024**3)

                    mem_reserved = torch.cuda.memory_reserved(i) / (1024**3)

                    print(f"      Memory Allocated: {mem_allocated:.2f} GB")

                    print(f"      Memory Reserved: {mem_reserved:.2f} GB")

                except:

                    pass

        else:

            print(f"   ❌ CUDA Available: NO (CPU only)")

            print(f"   Note: YOLO and PaddleOCR will run on CPU")

    except ImportError:

        print(f"   ❌ PyTorch not installed")

        print(f"   Install: pip install torch torchvision")

    except Exception as e:

        print(f"   ⚠️  Error checking PyTorch: {e}")

   

    # PaddleOCR backend

    print(f"\n📝 OCR Backend (PaddlePaddle):")

    try:

        import paddle

        print(f"   PaddlePaddle Version: {paddle.__version__}")

        if paddle.device.is_compiled_with_cuda():

            print(f"   ✅ PaddlePaddle: CUDA-enabled")

            try:

                gpu_count = paddle.device.cuda.device_count()

                print(f"   GPU Count: {gpu_count}")

            except:

                pass

        else:

            print(f"   ⚠️  PaddlePaddle: CPU-only")

       

        # Check MKL-DNN (CPU optimization)

        try:

            import paddle.fluid as fluid

            has_mkldnn = fluid.core.is_compiled_with_mkldnn()

            print(f"   MKL-DNN (CPU optimization): {'✅ Available' if has_mkldnn else '❌ Not available'}")

        except:

            print(f"   MKL-DNN: Unknown")

    except ImportError:

        print(f"   ❌ PaddlePaddle not installed")

        print(f"   Install: pip install paddlepaddle")

    except Exception as e:

        print(f"   ⚠️  Error checking PaddlePaddle: {e}")

   

    # YOLO/Ultralytics

    print(f"\n🔍 YOLO (Ultralytics):")

    try:

        import ultralytics

        from ultralytics import YOLO

        print(f"   Ultralytics Version: {ultralytics.__version__}")

        print(f"   ✅ YOLO available")

    except ImportError:

        print(f"   ❌ Ultralytics not installed")

        print(f"   Install: pip install ultralytics")

    except Exception as e:

        print(f"   ⚠️  Error checking Ultralytics: {e}")

   

    # Disk I/O

    disk = psutil.disk_usage('/')

    print(f"\n💿 Disk (Root):")

    print(f"   Total: {disk.total / (1024**3):.2f} GB")

    print(f"   Used: {disk.used / (1024**3):.2f} GB ({disk.percent}%)")

    print(f"   Free: {disk.free / (1024**3):.2f} GB")

   

    print("\n" + "="*70)





def detect_hardware_profile():

    """Detect hardware capabilities and return optimization profile."""

    profile = {

        'name': 'unknown',

        'cpu_cores': psutil.cpu_count(logical=True),

        'cpu_physical': psutil.cpu_count(logical=False),

        'ram_gb': psutil.virtual_memory().total / (1024**3),

        'has_gpu': False,

        'is_high_end': False

    }

   

    # Check GPU

    try:

        import torch

        profile['has_gpu'] = torch.cuda.is_available()

    except:

        pass

   

    # Classify system

    if profile['cpu_cores'] >= 12 and profile['ram_gb'] >= 16:

        profile['name'] = 'desktop_high'

        profile['is_high_end'] = True

    elif profile['cpu_cores'] >= 8 and profile['ram_gb'] >= 12:

        profile['name'] = 'laptop_good'

        profile['is_high_end'] = False

    elif profile['cpu_cores'] >= 4 and profile['ram_gb'] >= 8:

        profile['name'] = 'laptop_medium'

        profile['is_high_end'] = False

    else:

        profile['name'] = 'laptop_low'

        profile['is_high_end'] = False

   

    return profile





def recommend_settings(profile):

    """Recommend optimal settings based on hardware profile."""

    print("\n" + "="*70)

    print("RECOMMENDED SETTINGS")

    print("="*70)

   

    print(f"\n🔍 Detected Profile: {profile['name']}")

    print(f"   CPU Cores: {profile['cpu_cores']} ({profile['cpu_physical']} physical)")

    print(f"   RAM: {profile['ram_gb']:.1f} GB")

    print(f"   GPU: {'✅ Available' if profile['has_gpu'] else '❌ Not available (CPU only)'}")

    print(f"   Performance Class: {'High-End' if profile['is_high_end'] else 'Standard'}")

   

    # Recommend OCR workers

    if profile['is_high_end']:

        ocr_workers = 6

    elif profile['cpu_cores'] >= 8:

        ocr_workers = 4

    elif profile['cpu_cores'] >= 4:

        ocr_workers = 2

    else:

        ocr_workers = 1

   

    # Recommend YOLO settings

    if profile['has_gpu']:

        yolo_batch = 16

        yolo_device = 'cuda'

    else:

        yolo_batch = 1

        yolo_device = 'cpu'

   

    # Recommend image size

    if profile['ram_gb'] >= 16:

        pred_imgsz = 1024

    elif profile['ram_gb'] >= 12:

        pred_imgsz = 960

    else:

        pred_imgsz = 896

   

    # Recommend confidence multiplier

    if profile['is_high_end']:

        conf_mult = 1.0

    else:

        conf_mult = 0.9  # 10% more lenient

   

    # PaddleOCR settings

    if profile['has_gpu']:

        paddle_gpu = True

        paddle_mkldnn = False

        paddle_threads = 1

    else:

        paddle_gpu = False

        paddle_mkldnn = True

        paddle_threads = max(2, profile['cpu_cores'] // 2)

   

    print(f"\n⚙️  Recommended Configuration:")

    print(f"\n   # OCR Settings")

    print(f"   MAX_OCR_WORKERS = {ocr_workers}")

    print(f"   PADDLEOCR_USE_GPU = {paddle_gpu}")

    print(f"   PADDLEOCR_ENABLE_MKLDNN = {paddle_mkldnn}")

    print(f"   PADDLEOCR_CPU_THREADS = {paddle_threads}")

   

    print(f"\n   # YOLO Settings")

    print(f"   PRED_IMGSZ = {pred_imgsz}")

    print(f"   YOLO_DEVICE = '{yolo_device}'")

    print(f"   YOLO_BATCH_SIZE = {yolo_batch}")

   

    print(f"\n   # Detection Thresholds")

    print(f"   DETECTION_CONF_MULTIPLIER = {conf_mult}")

    print(f"   # Apply to CLASS_THRESH: threshold * {conf_mult}")

   

    print("\n" + "="*70)

   

    # Performance expectations

    print("\n📊 Expected Performance:")

    if profile['is_high_end']:

        print("   ✅ Excellent - Fast processing with high accuracy")

        print("   Expected time per page: 30-60 seconds")

    elif profile['name'] == 'laptop_good':

        print("   ✅ Good - Reasonable processing speed")

        print("   Expected time per page: 60-120 seconds")

    elif profile['name'] == 'laptop_medium':

        print("   ⚠️  Moderate - Slower but functional")

        print("   Expected time per page: 120-180 seconds")

    else:

        print("   ⚠️  Limited - May be slow")

        print("   Expected time per page: 180+ seconds")

   

    print("\n" + "="*70 + "\n")





def main():

    """Main test function."""

    print("\n🔧 Hardware Detection and Configuration Test\n")

   

    # Step 1: Print detailed hardware info

    print_hardware_info()

   

    # Step 2: Detect profile

    profile = detect_hardware_profile()

   

    # Step 3: Recommend settings

    recommend_settings(profile)

   

    # Warnings

    if not profile['has_gpu']:

        print("⚠️  WARNING: No GPU detected!")

        print("   YOLO and PaddleOCR will run on CPU (slower)")

        print("   Consider using a machine with NVIDIA GPU for better performance\n")

   

    if profile['ram_gb'] < 8:

        print("⚠️  WARNING: Low RAM detected!")

        print("   You may experience memory issues with large PDFs")

        print("   Consider closing other applications during processing\n")

   

    print("✅ Test complete!\n")





if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print("\n\n⚠️  Test interrupted by user\n")

    except Exception as e:

        print(f"\n\n❌ Error during test: {e}\n")

        import traceback

        traceback.print_exc()