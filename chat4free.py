#imports
from fastapi_poe import make_app
from modal import Image, Stub, asgi_app

from typing import AsyncIterable
import re

from fastapi_poe import PoeBot
from fastapi_poe.client import stream_request
from fastapi_poe.types import PartialResponse, ProtocolMessage, QueryRequest, SettingsRequest, SettingsResponse

#functions    
def remove_small_words(input_string):
    words = input_string.split()
    filtered_words = [word for word in words if len(word) > 2]
    return ' '.join(filtered_words)

#classes
class BotDefinitions(PoeBot):

    async def get_response(
        self, request: QueryRequest
    ) -> AsyncIterable[PartialResponse]:

        #default settings
        chatbot = "solar-mini"
        imgbot = ""
        imgstyle = "stylized pop anime line-art"
        
        #separate commands from prompts
        commands: List[str] = []
        for chat in request.query:
            command = ""
            if chat.content.startswith("["):
                closebracket = chat.content.find("]")
                if closebracket < 1:
                    command = chat.content[1:].strip().lower()
                    chat.content = ""
                else:
                    command = chat.content[1:closebracket].strip().lower()
                    chat.content = chat.content[closebracket+1:].strip()
                if "mixtral" in command: chatbot = "mixtral-8x7b-groq"
                if "claude" in command: chatbot = "claude-instant"
                if "chatgpt" in command: chatbot = "chatgpt"
                if "c100" in command: chatbot = "claude-instant-100k"
                if "solar" in command: chatbot = "solar-mini"
                if "gemini" in command: chatbot = "gemini-pro"
                if "groq" in command: chatbot = "llama-2-70b-groq"
                if "qwen" in command: chatbot = "qwen-72b-chat"
                if "bot" in command: chat.role = "bot"
                if "system" in command:
                    if len(commands) == 0:
                        chat.role = "system"
                    else:
                        chat.role = "bot"
                if "style" in command:
                    imgstyle = chat.content[:35]
                    chat.content = ""
                
            #ignore images included in previous replies
            chat.content = re.sub('!?\[[^\]]+\]\([^\)]+\)','',chat.content).replace("\n\n\n\n","\n\n")
            commands.append(command)
        
        #read last command
        if "selfie" in commands[-1] or "pic" in commands[-1]: imgbot = "playground-v2"
        if "sdxl" in commands[-1]: imgbot = "stablediffusionxl"

        #remove blank chat entries
        newchat: List[ProtocolMessage] = []
        for chat in request.query:
            if chat.content.strip() != "":
                newchat.append(chat)
        request.query = newchat
     
        if len(imgbot) > 0:
            # create a prompt for an image (up to 220 characters)
            yield PartialResponse(text="...getting my camera out")
            origprompt = request.query[-1].content
            request.query[-1].content = f'{request.query[-1].content} [Answer with a 100-word description, emphasizing emotion and facial expressions, removing sexual content such as lingerie or collars. For example "An attractive woman, nice smile, happy to talk to you"]'
            chunks: List[str] = []
            themelength = 0
            themebot = "solar-mini"
            if themebot == chatbot: themebot = "mixtral-8x7b-groq"
            async for msg in stream_request(request, themebot, request.access_key):
                snippet = re.sub('[^A-Za-z\s]', ' ', msg.text)
                if len(snippet) > 0:
                    chunks.append(snippet)
                    themelength += len(snippet)
                if themelength > 300:
                    break
            #remove filler words
            theme = remove_small_words("".join(chunks))[:220]
            theme = f"{imgstyle}, {theme[:theme.rfind(' ')].strip(',')}"
            yield PartialResponse(text=f"\n\n{theme} ({len(theme)} characters)")
            
            # generate image                
            yield PartialResponse(text=f"\n\n...snapping a photo")
            request.query[-1].content = theme
            imagelink = ""
            async for msg in stream_request(request, imgbot, request.access_key):
                imagelink=msg.text
            if "[" not in imagelink: 
                imagelink = ""
                yield PartialResponse(text=f"\n\nOh, I can't show you that!")
        
            # generate a text and image response
            if request.query[-1].content == "" or request.query[-1].role != "user":
                # image only
                if imagelink != "": yield PartialResponse(text = f"{imagelink}", is_replace_response = True)
                return
            else:
                # text followed by image
                if imagelink != "": 
                    request.query[-1].content = f"<system>Continue, taking into account the generated image and the user's message.</system>\n\n<image_description>{theme}</image_description>\n\n<user_message>{origprompt}</user_message>"
                else:
                    request.query[-1].content = origprompt
                replace = True
                async for msg in stream_request(request, chatbot, request.access_key):
                    yield PartialResponse(text = msg.text, is_replace_response = replace)
                    if msg.text != "" :
                        replace = False
                if imagelink != "": yield PartialResponse(text = f"\n\n\n\n{imagelink}")
            
        else: 
        
            #generate a text-only response
            if request.query[-1].content == "" or request.query[-1].role != "user":
                yield PartialResponse(text = f"[{chatbot}] ")
            else:
                replace = True
                async for msg in stream_request(request, chatbot, request.access_key):
                    yield PartialResponse(text = msg.text, is_replace_response = replace)
                    if msg.text != "" :
                        replace = False
            
    async def get_settings(self, setting: SettingsRequest) -> SettingsResponse:

        #details about your bot
        return SettingsResponse(
            #this can list a max of 10, even if the bot only ever calls one or two
            server_bot_dependencies={
                "mixtral-8x7b-groq":1,
                "claude-instant":1,
                "chatgpt":1,
                "claude-instant-100k":1,
                "solar-mini":1,
                "gemini-pro":1,
                "llama-2-70b-groq":1,
                "qwen-72b-chat":1,
                "playground-v2":1,
                "stablediffusionxl":1,
            },
            #introduction_message="",
        )

#Execute
bot = BotDefinitions()
image = Image.debian_slim().pip_install_from_requirements("requirements.txt")
stub = Stub("chat4free")
@stub.function(image=image)
@asgi_app()
def fastapi_app():
    app = make_app(bot, access_key="---comes from bot settings page---")
    return app
