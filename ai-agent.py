import os

# 載入 Gradio
import gradio as gr

# 載入 Langchain Groq
from langchain_groq import ChatGroq

# 載入 Langchain Prompts
from langchain.prompts import (
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    ChatPromptTemplate,
    MessagesPlaceholder,
    PromptTemplate
)

# 載入 Langchain Agents
from langchain.agents import create_tool_calling_agent
from langchain.agents import AgentExecutor
from langchain.tools import tool

# 載入 Langchain Memory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory

# 載入 Langchain Callback
from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

# 載入 Langchain OpenAI
from langchain_openai import (
    ChatOpenAI
)

# 載入核心模組
from modules.core_module import(
    config
)

# 載入 LlamaIndex
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.llms.openai import OpenAI
from llama_index.core.node_parser import SentenceSplitter

# Groq 初始化
os.environ["GROQ_API_KEY"] = config.get(
    'groq',
    'api_key'
)

# OpenAI 初始化
os.environ["OPENAI_API_KEY"] = config.get(
    'openai',
    'api_key'
)

# LLM 初始化
""" model = ChatGroq(model_name=config.get(
        'groq',
        'model'
    ),
    temperature=0.5,
    max_tokens=3000,
    n=1,
    streaming=True,
    callbacks=CallbackManager([StreamingStdOutCallbackHandler()])
)
"""
model = ChatOpenAI(model_name=config.get(
        'openai',
        'model'
    ),
    temperature=0.5,
    max_tokens=3000,
    n=1,
    streaming=True,
    callbacks=CallbackManager([StreamingStdOutCallbackHandler()])
)

# LlamaIndex 初始化
llm = OpenAI(model=config.get(
        'openai',
        'model'
))
documents = SimpleDirectoryReader(input_dir="./data").load_data()
Settings.text_splitter = SentenceSplitter(chunk_size=1024, chunk_overlap=20)
index = VectorStoreIndex.from_documents(
    documents,
    transformations=[SentenceSplitter(chunk_size=1024, chunk_overlap=20)],
)
chat_engine = index.as_chat_engine(chat_mode="openai", llm=llm, verbose=True)

# 工具初始化
@tool
async def rag_answer(message: str) -> str:
    '''
    詢問任何疑難雜症
    詢問各式各樣問題
    '''
    # 輸入文字處理
    message = message.strip().replace('\n', '')
    answer = chat_engine.chat(message)
    return answer

# Tools 設定
tools = [rag_answer]
llm_forced_to_use_tool = model.bind_tools(tools, tool_choice="any")

# Prompt 初始化
template = '''
如果是寒暄或禮貌性提問，不使用工具與記憶，只回應對應的禮貌性回答
除了寒暄或禮貌性提問請優先透過工具回答問題
請潤飾所有透過工具取得的內容為你的語氣
不管多少字都只用繁體中文回答
'''
system_message_prompt = SystemMessagePromptTemplate.from_template(template)
human_template = '''
{input}
如果是透過工具取得的內容用你的語氣進行潤飾與擴增
如果是透過工具取得的內容回答不用任何帶解釋說明與格式
如果是寒暄或禮貌性提問，不使用工具與記憶，只回應對應的禮貌性回答
只用繁體中文回答
'''
human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)
prompt = ChatPromptTemplate.from_messages([
    system_message_prompt,
    MessagesPlaceholder(variable_name='chat_history', optional=True),
    HumanMessagePromptTemplate(prompt=PromptTemplate(input_variables=['input'], template=human_template)),
    MessagesPlaceholder(variable_name='agent_scratchpad')
])

# 記憶初始化
session_id = '<foo>'
store = {}
def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

# 機器人開講
async def Chat(message, history, request: gr.Request):

    # 使用者 Session Hash
    if(request):
        session_id = request.session_hash
    print("\n\n===== User Session ID =====\n\n{}".format(session_id))

    # 使用者輸入
    print("\n===== User input =====\n\n{}\n\n".format(message))

    if not len(message):
        print("\n\n===== AI response =====\n\n哈囉，請問您想問些什麼呢?\n\n")
        yield "哈囉，請問您想問些什麼呢?"

    else:
        # Agent 設定
        agent = create_tool_calling_agent(llm_forced_to_use_tool, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools,verbose=False)
        agent_with_chat_history = RunnableWithMessageHistory(
            agent_executor,
            get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history"
        )

        # 輸出結果
        partial_message = ""
        count = 0
        async for event in agent_with_chat_history.astream_events(
            {"input": message},
            config={"configurable": {"session_id": session_id}},
            version="v1",
        ):
            if count == 0:
                yield "(思考中...)"

            kind = event["event"]
            if kind == "on_chat_model_stream":
                count += 1
                if count == 1:
                    partial_message = event['data']['chunk'].content
                else:
                    partial_message += event['data']['chunk'].content
                yield partial_message
        print("\n\n===== AI response =====\n\n{}\n\n".format(partial_message))

chatbot = gr.ChatInterface(
    Chat,
    chatbot=gr.Chatbot(
        label="問答記錄",
        bubble_full_width=False,
        avatar_images=(None, (os.path.join(os.path.dirname(__file__), "img/AIP.jpg"))),
        elem_id="chatbot"
    ),
    textbox=gr.Textbox(placeholder="輸入任何想問的問題", container=False, scale=7),
    title="AI 小助理",
    description=None,
    theme="ParityError/Anime",
    examples=["黑神話悟空遊戲中的六根分別有哪些場景?", "蘋果這次發表會有哪些新玩意兒?", "RAG的技術細節有哪些?"],
    cache_examples=False,
    submit_btn="發問 ▶️",
    retry_btn=None,
    undo_btn=None,
    clear_btn=None,
    stop_btn="停止 ⏸",
    css="""
    footer {visibility: hidden}
    #chatbot {
        flex-grow: 1 !important;
        overflow: auto !important;
    }
    """,
    fill_width=True,
    fill_height=True
).queue()

if __name__ == "__main__":
    chatbot.launch()
