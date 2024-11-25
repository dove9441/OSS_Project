from langchain_community.document_loaders import WebBaseLoader
from langchain.chains.summarize import load_summarize_chain
from langchain.prompts import PromptTemplate
from langchain.text_splitter import CharacterTextSplitter
import dotenv
import os
from langchain_groq import ChatGroq
from langchain.docstore.document import Document # 텍스트를 document 객체로 변환
import time
import queue as q
import threading
import json
from fastapi import Request, FastAPI, Response
from langchain.chains import LLMChain
dotenv.load_dotenv()

##### 기능 함수 구현 단계 #####
# 메시지 전송
def textResponseFormat(bot_response):
    #print('------------BOT_RESONSE-------------')
    #print(bot_response)
    response = {"version":"2.0", "template":{"outputs":[{"simpleText":{"text":bot_response}}], "quickReplies":[]}}
    return response

# 사진 전송
def imageResponseFormat(bot_response, prompt):
    output_text = prompt + "내용에 관한 이미지입니다"
    response = {"version":"2.0", "template":{"outputs":[{"simpleImage":{"imageUrl":bot_response, "altText":output_text}}], "quickReplies":[]}}
    return response

# 응답 초과 시 답변
def timeover():
    response = { "version":"2.0", "template":{
        "outputs":[
            {
                "simpleText":{
                    "text":"아직 제가 생각이 끝나지 않았어요 🙏🙏 \n잠시 후 아래 말풍선을 눌러주세요 👆"
                }
            }
        ],
        "quickReplies":[
            {
                "action":"message",
                "label":"생각 다 끝났나요? 🙋‍♂️",
                "messageText":"생각 다 끝났나요?"
            }
        ]
    }}
    return response




# 텍스트 파일 초기화
def dbReset(filename):
    with open(filename, 'w') as f:
        f.write("")


##### 서버 생성 단계 #####

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "kakaoTest"}

@app.post("/chat/")
async def chat(request: Request):
    kakaorequest = await request.json()
    return mainChat(kakaorequest)

#### 메인 함수 구현 단계 ######

# 메인 함수
def mainChat(kakaorequest):
    #print(json.dumps(kakaorequest, indent=2))
    run_flag = False
    start_time = time.time()
    #kakaorequest = json.loads(event['body'])
    # 응답 결과를 저장하기 위한 텍스트 파일 생성
    cwd = os.getcwd()
    filename = cwd + "/botlog.txt"
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            f.write("")
    else:
        print("File Exists")

    # 답변 생성 함수 실행
    response_queue = q.Queue()
    request_respond = threading.Thread(target=responseOpenAI, args = (kakaorequest, response_queue, filename))
    request_respond.start()

    # 답변 생성 시간 체크
    while (time.time() - start_time < 3.5):
        if not response_queue.empty():
            # 3.5초 안에 답변이 완성되면 바로 값을 반환
            response = response_queue.get()
            run_flag = True
            break
        # 안정적인 구동을 위한 딜레이 타임 설정
        time.sleep(0.01)
    # 응답이 3.5초 이내에 오지 않으면
    if run_flag == False:
        # 생각 끝남버튼 출력함수 호출
        response = timeover()
    return Response(content=json.dumps(response), media_type='application/json')

# 답변/사진 요청 및 응답 확인 함수
def responseOpenAI(request, response_queue, filename):
    #print(json.dumps(request, indent=2))
    # 사용자가 버튼을 클릭하여 답변 완성 여부를 다시 봤을 시
    if '생각 다 끝났나요?' in request["userRequest"]["utterance"]:
        # 텍스트 파일 열기
        with open(filename) as f:
            last_update = f.read()
        # 텍스트 파일 내 저장된 정보가 있을 경우
        if len(last_update.split()) > 1:
            kind, bot_res, prompt = last_update.split()[0], last_update.split()[1], last_update.split()[2]
            if kind == "img":
                response_queue.put(imageResponseFormat(bot_res, prompt))
            else:
                response_queue.put(textResponseFormat(bot_res))
            dbReset(filename)

    # LLM 답변을 요청한 경우
    elif '/ask' in request["userRequest"]["utterance"]: 
        dbReset(filename)
        prompt = request["userRequest"]["utterance"].replace("/ask", "")
        bot_res = getRagResponse_LLAMA(prompt)#getTextFromLLAMA(prompt)
        response_queue.put(textResponseFormat(bot_res))

        save_log = "ask" + " " + str(bot_res) + " " + str(prompt)
        with open(filename, 'w') as f:
            f.write(save_log)

    # 아무 답변 요청이 없는 채팅일 경우
    else:
        # 기본 response 값
        defaultText = "아무 답변 요청이 없는 메시지입니다."
        base_response = {
                            "version": "2.0",
                            "template": {
                                "outputs": [
                                {
                                    "simpleText": {
                                        "text": "default"
                                    }
                                }
                                ]
                            }
                            }
        response_queue.put(textResponseFormat(defaultText))




def getTextFromLLAMA(prompt):
    llm = ChatGroq(model="llama-3.1-8b-instant")#llama-3.1-70b-versatile")
    combine_prompt = PromptTemplate(input_variables=['text'], template="You are an participatnt in 1:1 dialogue. Response about quesition. : {text}.")
    chain = LLMChain(llm=llm, prompt=combine_prompt, verbose=True)
    response = chain.invoke({'text':prompt})
    return response['text']



def getSummeryFromLLM(text):
    # 각 Chunk 단위의 템플릿
    template = '''다음의 내용을 한글로 요약해줘:
    {text}
    '''
    # 전체 문서(혹은 전체 Chunk)에 대한 지시(instruct) 정의
    combine_template = '''{text}

    요약의 결과는 다음의 형식으로 작성해줘.
    제목: 기사 제목
    요약: 3줄로 요약된 내용
    세부내용: 주요내용을 작성
    '''
    # 템플릿 생성
    prompt = PromptTemplate(template=template, input_variables=['text'])
    combine_prompt = PromptTemplate(template=combine_template, input_variables=['text'])

    # LLM 객체 생성
    llm = ChatGroq(model="llama-3.1-8b-instant")#llama-3.1-70b-versatile")
    #llm = ChatOpenAI(temperature=0, model_name='gpt-3.5-turbo-16k')

    # 요약을 도와주는 load_summarize_chain
    chain = load_summarize_chain(llm,  map_prompt=prompt, combine_prompt=combine_prompt, chain_type="map_reduce", verbose=True)
    text_docs = Document(page_content=text)
    summerized_msg = chain.invoke([text_docs])
    return summerized_msg


################################# WEBSEARCH RAG TEST ######################
import streamlit as st
from langchain_community.document_loaders import AsyncChromiumLoader
from langchain_community.document_transformers import BeautifulSoupTransformer
from duckduckgo_search import DDGS
import re

# performs DuckDuckGo search, urls are extracted and status checked
# 
def ddg_search(query):
    results = DDGS().text(query, max_results=5)
    urls = []
    for result in results:
        url = result['href']
        urls.append(url)

    docs = get_page(urls)

    content = []
    for doc in docs:
        page_text = re.sub("\n\n+", "\n", doc.page_content)
        text = truncate(page_text)
        content.append(text)

    return content

# retrieves pages and extracts text by tag
def get_page(urls):
    loader = AsyncChromiumLoader(urls)
    html = loader.load()

    bs_transformer = BeautifulSoupTransformer()
    docs_transformed = bs_transformer.transform_documents(html, tags_to_extract=["p"], remove_unwanted_tags=["a"])

    return docs_transformed

# helper function to reduce the amount of text
def truncate(text):
    words = text.split()
    truncated = " ".join(words[:400])

    return truncated

def getRagResponse_LLAMA(query):
    search_results = ddg_search(query)
    if not search_results:
        return "No search results found or an error occurred."

    # LLM initialization
    llm = ChatGroq(model="llama-3.1-8b-instant")  # Ensure this model exists and is configured

    # Prompt template
    combine_prompt = PromptTemplate(
        input_variables=['text', 'search_results'],
        template="You are a participant in a 1:1 dialogue. Respond to the question using the search results. "
                 "Question: {text}\n"
                 "Search Results: {search_results}\n"
                 "Answer:"
    )

    # Chain setup
    chain = LLMChain(llm=llm, prompt=combine_prompt, verbose=True)
    try:
        response = chain.invoke({'text': query, 'search_results': "\n".join(search_results)})
        return response['text']
    except Exception as e:
        print(f"Error during LLM invocation: {e}")
        return "An error occurred while generating the response."




sampletext = """
GOP senators could pay a price for a prolonged confirmation fight
If Trump sticks with his pick, Republican senators feeling the MAGA movement’s pressure could be forced to defend Gaetz for weeks. That could land them in a tricky spot. Despite the threat that senators could face primaries if they break with the president-elect, votes for a compromised nominee could also haunt those seeking reelection in statewide races in 2026.

Cramer is raising logical political issues. Yet Trump is such a unique figure that the normal calculations may not apply.

Matt Gaetz speaks during a news conference at the US Capitol on February 13.
Related article
Women testified to House panel that they were paid for sexual favors by Gaetz, lawyer says

Historically, a conventional president might see the uproar surrounding his pick, assess the shifting political sands and quietly withdraw support — reasoning that there’s little point in damaging their precious authority before their term even starts. Such political capital might be better spent on aggressively implementing an agenda in the first 100 days than on a pick who could already be doomed. In Trump’s case, sacrificing Gaetz could also ease the way for other provocative Cabinet picks, including Fox News anchor Pete Hegseth, whom Trump wants to serve as defense secretary, and Robert F. Kennedy Jr., the vaccine skeptic he wants to run the Health and Human Services Department. Senators might be just about ready to defy the president-elect on one selection, but a wholesale rejection of his choices would be political folly for them.

But Trump is also making this about far more than Gaetz, creating a test of power that reflects his own self-confidence, the balance of power in the new Congress and his belief that the GOP Senate should be at his service and not be a moderating force.

The president-elect’s unorthodox pick of the Florida Republican – and the muscle that he’s already put into his candidacy – means that Trump may soon approach the point where it will cost him more political capital to fold on Gaetz than to keep trying to get him installed – whatever it takes.

Ever since Trump shocked Capitol Hill and delighted his most committed supporters by selecting an ultra loyalist who has said the FBI should be abolished if it won’t “come to heel,” it’s been clear that this pick is different. The president-elect could have chosen just about anyone in Washington, and they would have been less controversial than Gaetz.

But the Florida Republican shares the president-elect’s belief that the Justice Department has victimized Trump and needs to be purged."""





        