"""
远程重启 MinerU Docker 服务脚本
通过SSH连接到环北服务器，执行Docker重启命令
"""
import paramiko
import sys
from datetime import datetime


class SSHExecutor:
    """SSH命令执行器"""
    
    def __init__(self, host, port, username, password):
        """
        初始化SSH连接参数
        
        Args:
            host: 服务器IP地址
            port: SSH端口
            username: 用户名
            password: 密码
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        
    def connect(self):
        """建立SSH连接"""
        try:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 正在连接到服务器 {self.host}:{self.port}...")
            
            self.client = paramiko.SSHClient()
            # 自动添加主机密钥
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # 连接服务器
            self.client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=10
            )
            
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ 连接成功!")
            return True
            
        except paramiko.AuthenticationException:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✗ 认证失败，请检查用户名和密码")
            return False
        except paramiko.SSHException as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✗ SSH连接错误: {e}")
            return False
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✗ 连接失败: {e}")
            return False
    
    def execute_command(self, command, show_output=True):
        """
        执行单条命令
        
        Args:
            command: 要执行的命令
            show_output: 是否实时显示输出
            
        Returns:
            tuple: (exit_code, stdout, stderr)
        """
        try:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 执行命令: {command}")
            print("-" * 60)
            
            # 执行命令
            stdin, stdout, stderr = self.client.exec_command(command)
            
            # 获取退出码
            exit_code = stdout.channel.recv_exit_status()
            
            # 读取输出
            stdout_lines = stdout.read().decode('utf-8')
            stderr_lines = stderr.read().decode('utf-8')
            
            # 显示输出
            if show_output:
                if stdout_lines:
                    print(stdout_lines)
                if stderr_lines:
                    print(f"错误输出:\n{stderr_lines}", file=sys.stderr)
            
            print("-" * 60)
            
            if exit_code == 0:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ 命令执行成功 (退出码: {exit_code})")
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✗ 命令执行失败 (退出码: {exit_code})")
            
            return exit_code, stdout_lines, stderr_lines
            
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✗ 执行命令时出错: {e}")
            return -1, "", str(e)
    
    def execute_commands(self, commands):
        """
        按顺序执行多条命令
        
        Args:
            commands: 命令列表
            
        Returns:
            bool: 是否全部执行成功
        """
        all_success = True
        
        for i, command in enumerate(commands, 1):
            print(f"\n{'='*60}")
            print(f"执行步骤 {i}/{len(commands)}")
            print(f"{'='*60}")
            
            exit_code, stdout, stderr = self.execute_command(command)
            
            if exit_code != 0:
                all_success = False
                print(f"\n⚠️  警告: 第 {i} 步执行失败，但继续执行后续命令...")
        
        return all_success
    
    def close(self):
        """关闭SSH连接"""
        if self.client:
            self.client.close()
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 连接已关闭")


def restart_mineru_docker():
    """重启 MinerU Docker 服务"""
    
    # 服务器配置
    SERVER_CONFIG = {
        'host': '10.11.76.212',
        'port': 22,
        'username': 'root',
        'password': '1s3LwmnznxQ='
    }
    
    # 要执行的命令列表
    commands = [
        'cd /data/mineru-api',
        'docker-compose down',
        'docker-compose up -d'
    ]
    
    # 组合成单条命令（使用 && 确保前一条成功才执行下一条）
    combined_command = ' && '.join(commands)
    
    print("="*60)
    print("MinerU Docker 服务重启脚本")
    print("="*60)
    print(f"服务器: {SERVER_CONFIG['host']}")
    print(f"用户: {SERVER_CONFIG['username']}")
    print(f"操作: 重启 /data/mineru-api 下的 Docker 服务")
    print("="*60)
    
    # 创建SSH执行器
    executor = SSHExecutor(**SERVER_CONFIG)
    
    try:
        # 连接服务器
        if not executor.connect():
            print("\n❌ 无法连接到服务器，脚本终止")
            return False
        
        # 执行组合命令
        exit_code, stdout, stderr = executor.execute_command(combined_command)
        
        # 检查结果
        if exit_code == 0:
            print("\n" + "="*60)
            print("✅ MinerU Docker 服务重启成功!")
            print("="*60)
            return True
        else:
            print("\n" + "="*60)
            print("❌ MinerU Docker 服务重启失败!")
            print("="*60)
            return False
            
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断操作")
        return False
    except Exception as e:
        print(f"\n❌ 发生异常: {e}")
        return False
    finally:
        executor.close()


if __name__ == "__main__":
    try:
        success = restart_mineru_docker()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 程序异常退出: {e}")
        sys.exit(1)
