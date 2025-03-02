import ollama
from wxauto import WeChat
import time
import configparser
import threading
from queue import Queue
import os

# 读取配置文件
def read_config():
    config = configparser.ConfigParser()
    with open('config.ini', encoding='utf-8') as config_file:
        config.read_file(config_file)
    return config

config = read_config()

# 配置 ollama 服务的地址和端口
OLLAMA_HOST = config['ollama']['host']
OLLAMA_PORT = config['ollama']['port']
OLLAMA_MODEL = config['ollama']['model']

# 初始化微信对象
wx = WeChat()

# 定义需要监听的联系人或群的列表
listen_friends = config['listen']['friends'].split(',') if config['listen']['friends'] else []
listen_groups = config['listen']['groups'].split(',') if config['listen']['groups'] else []

# 获取配置文件中重新加载间隔时间
reload_interval = int(config['reload']['interval'])

# 向 ollama 发送请求并获取回复
def get_ollama_response(prompt):
    try:
        # 创建 ollama 客户端
        client = ollama.Client(host=f"http://{OLLAMA_HOST}:{OLLAMA_PORT}")
        # 发起聊天请求
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.7, "max_tokens": 200}  # 根据需要调整参数
        )
        # 提取 ollama 的回复内容
        if response and "message" in response:
            return response["message"]["content"]
        else:
            return "抱歉，我无法获取回复。"
    except Exception as e:
        print(f"请求 ollama 服务时出错：{e}")
        return "抱歉，我无法获取回复。"

# 处理消息的函数
def process_messages(ollama_queue):
    while True:
        # 获取监听到的消息
        msgs = wx.GetListenMessage()
        if msgs:
            for chat in msgs:
                who = chat.who  # 获取聊天窗口名
                one_msgs = msgs.get(chat, [])  # 获取特定聊天窗口的消息列表
                if one_msgs:
                    msg = one_msgs[-1]  # 只获取最后一次发送过来的消息
                    msg_type = msg.type  # 获取消息类型
                    content = msg.content.replace('\n', '').strip()  # 获取消息内容并去除换行符和前后空格
                    if msg_type == "friend" or msg_type == "group":  # 如果是好友消息或群消息
                        print(f"收到消息：{who} - {content}")
                        ollama_queue.put((who, content))  # 将消息放入队列中
                    # 忽略语音消息
        time.sleep(1)  # 暂停1秒后继续循环

# 处理 ollama 回复的函数
def handle_ollama_responses(ollama_queue):
    while True:
        if not ollama_queue.empty():
            who, content = ollama_queue.get()
            response = get_ollama_response(content)  # 获取 ollama 的回复
            print(f"发送回复：{who} - {response}")
            try:
                wx.SendMsg(response, who=who)  # 将回复发送回聊天窗口
            except TypeError as e:
                print(f"发送消息时出错：{e}")
            ollama_queue.task_done()  # 通知队列任务已完成
        time.sleep(1)  # 暂停1秒后继续循环

# 重新加载配置的函数
def reload_config():
    global config, OLLAMA_HOST, OLLAMA_PORT, OLLAMA_MODEL, listen_friends, listen_groups
    config = read_config()
    OLLAMA_HOST = config['ollama']['host']
    OLLAMA_PORT = config['ollama']['port']
    OLLAMA_MODEL = config['ollama']['model']
    new_listen_friends = config['listen']['friends'].split(',') if config['listen']['friends'] else []
    new_listen_groups = config['listen']['groups'].split(',') if config['listen']['groups'] else []

    # 移除旧的监听
    for friend in listen_friends:
        if friend not in new_listen_friends:
            wx.RemoveListenChat(who=friend)
    for group in listen_groups:
        if group not in new_listen_groups:
            wx.RemoveListenChat(who=group)

    # 添加新的监听
    for friend in new_listen_friends:
        if friend not in listen_friends:
            wx.AddListenChat(who=friend)
    for group in new_listen_groups:
        if group not in listen_groups:
            wx.AddListenChat(who=group)

    listen_friends = new_listen_friends
    listen_groups = new_listen_groups
    print("配置文件已重新加载。")

# 重新加载配置的函数，仅使用时间间隔来检查配置文件是否被修改
def periodic_reload_config():
    last_modified_time = 0
    while True:
        if reload_interval > 0:
            try:
                modified_time = os.path.getmtime('config.ini')
                if modified_time > last_modified_time:
                    last_modified_time = modified_time
                    reload_config()
            except Exception as e:
                print(f"检查配置文件时出错：{e}")
        time.sleep(reload_interval)  # 根据配置文件中的间隔时间来检查

# 主循环，持续监听和处理微信消息
def main():
    ollama_queue = Queue()

    # 添加每一个好友的监听设置
    for friend in listen_friends:
        wx.AddListenChat(who=friend)

    # 添加每一个群的监听设置
    for group in listen_groups:
        wx.AddListenChat(who=group)

    # 创建并启动处理消息的线程
    thread_process = threading.Thread(target=process_messages, args=(ollama_queue,))
    thread_process.daemon = True
    thread_process.start()

    # 创建并启动处理 ollama 回复的线程
    thread_ollama = threading.Thread(target=handle_ollama_responses, args=(ollama_queue,))
    thread_ollama.daemon = True
    thread_ollama.start()

    # 创建并启动周期性重新加载配置的线程
    thread_periodic_reload = threading.Thread(target=periodic_reload_config)
    thread_periodic_reload.daemon = True
    thread_periodic_reload.start()

    # 保持主程序运行
    try:
        while True:
            time.sleep(1)  # 主线程暂停1秒后继续循环
    except KeyboardInterrupt:
        print("程序已终止。")

if __name__ == "__main__":
    main()
