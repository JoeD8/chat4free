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
        chatbot = "mixtral-8x7b-chat"
        imgbot = ""
        
        #separate commands from prompts
        commands: List[str] = []
        for chat in request.query:
            command = ""
            if chat.content.startswith("["):
                closebracket = chat.content.find("]")
                if closebracket < 1:
                    command = chat.content[1:].strip()
                    chat.content = ""
                else:
                    command = chat.content[1:closebracket].strip()
                    chat.content = chat.content[closebracket+1:].strip()
            #ignore images included in previous replies
            chat.content = re.sub('!?\[[^\]]+\]\([^\)]+\)','',chat.content).replace("\n\n\n\n","\n\n")
            commands.append(command.strip().lower())
        
        #read last command
        if "claude" in commands[-1]:
            chatbot = "claude-instant"
        if "chatgpt" in commands[-1]:
            chatbot = "chatgpt"
        if "pic" in commands[-1]:
            imgbot = "stablediffusionxl"
        if "selfie" in commands[-1]:
            imgbot = "playground-v2"

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
            request.query[-1].content = f'{request.query[-1].content} [respond with up to 100 words describing a picture, e.g., "a selfie of an attractive woman, nice smile, happy to talk to you --no disfigured, ugly, boring, serious"]'
            chunks: List[str] = []
            themelength = 0
            async for msg in stream_request(request, "mixtral-8x7b-chat", request.access_key):
                snippet = re.sub('[^A-Za-z\s]', ' ', msg.text)
                if len(snippet) > 0:
                    chunks.append(snippet)
                    themelength += len(snippet)
                if themelength > 300:
                    break
            #remove filler words
            theme = remove_small_words("".join(chunks))[:220]
            theme = f"{theme[:theme.rfind(' ')].strip(',')}"
            yield PartialResponse(text=f"\n\n{theme} ({len(theme)} characters)")
            
            # generate image                
            yield PartialResponse(text=f"\n\n...snapping a photo")
            request.query[-1].content = theme
            imagelink = ""
            async for msg in stream_request(request, imgbot, request.access_key):
                imagelink=msg.text
        
            # generate and display story
            request.query[-1].content = f"[implied imagery: {theme}] {origprompt}"
            replace = True
            async for msg in stream_request(request, chatbot, request.access_key):
                yield PartialResponse(text = msg.text, is_replace_response = replace)
                if msg.text != "" :
                    replace = False
            
            # display image
            yield PartialResponse(text = f"\n\n---\n\n{imagelink}")
            
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
                "mixtral-8x7b-chat":2,
                "chatgpt":1,
                "claude-instant":1,
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
