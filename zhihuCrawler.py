from pyppeteer import launch
from pyppeteer.errors import PageError, NetworkError
import random
import asyncio
import requests
import logging
import re
from bs4 import BeautifulSoup
DEFAULT_PROXY_POOL = 'http://127.0.0.1:5555/random'

class ZhiHuQAPage():
    def __init__(self, url, proxy_pool=None) -> None:
        self.url = url
        if proxy_pool != None:
            self.proxy_pool = proxy_pool
        else:
            self.proxy_pool = DEFAULT_PROXY_POOL
    
    async def try_visit(self, max_repeats=300, headless=False, need_proxy=True ,userDataDir=None, width=1366, height=768, timeout=300):
        '''
        尝试打开 self.url 指定的 page, 尝试默认最多 300 次
        '''
        for i in range(max_repeats):
            if i % 5  == 0 :
                logging.info(f"try visit {self.url} ,repeat {i} times")
            try:
                if need_proxy:
                    proxy = requests.get(self.proxy_pool).text.strip()
                else:
                    proxy = None
                # 页面内容太多时，使用无头浏览器，然后没过一段时间截图来显示页面内容,无头一直无法通过代理成功连接
                # 是浏览器头的问题吗，（验证的问题，不同代理为什么也要验证），经有头验证发现不是
                # 或者是单纯20个代理全关挂掉了？,无头情况下三十个未成功（3000个回答的那个）
                browser = await launch(
                    headless=headless,
                    userDataDir=None,
                    args=[
                        '--disable-infobars',
                        f'--window-size={width}, {height}',
                        f'--proxy-server={proxy}',
                    ]
                )
                page = await browser.newPage()
                await page.setViewport({'width':width, 'height':height})
                await page.evaluateOnNewDocument(
                    'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
                    )
                await page.goto(self.url, {'timeout' :timeout*1000})    
                
                # await page.goto("https://www.zhihu.com/question/628908067")  
                # 无cookie时，关闭登录界面,可能会跳出验证页面，此时直接关闭
                # 等待加载
                await asyncio.sleep(20)
                
                if await PageOperation().isRobotVerify(page) : 
                    await browser.close()
                    logging.info("存在验证-关闭浏览器")
                else :
                    await page.click('button[aria-label="关闭"]')
                    logging.info(f"success when repeat the {i} time, the proxy is {proxy}")
                    break    
            except PageError:
                logging.info(f"{PageError}")
                await browser.close()
                
            except TimeoutError:
                logging.info(f"{TimeoutError}")
                await browser.close()

            except NetworkError:
                logging.info(f"{NetworkError}")
                await browser.close()
                
        return browser, page


class ZhiHuSearch():
    
    @staticmethod
    async def frontPage(userDataDir='./PyppeteerTest/ZhiHuCookie', width=1366, height=768):
        '''
        实现知乎首页搜索 query，该函数需要先登录知乎账号，
        保证./PyppeteerTest/ZhihuCookie下存有用户信息,
        '''
        browser = await launch(
        headless=False, 
        userDataDir=userDataDir,
        args=[
            '--disable-infobars',
            f'--window-size={width},{height}'
            ])
        page = await browser.newPage()
        await page.setViewport({'width':width, 'height':height})
        # 绕过 webdriver 的检测
        await page.evaluateOnNewDocument(
            'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
            )
        await page.goto("https://www.zhihu.com")
        return page
    
    @staticmethod
    async def search(page, query="大模型", width=1366, height = 768, queryLengthLimit=20):
        '''
        query 长度小于等于10
        '''
        input_selector = 'input#Popover1-toggle'
        await page.type(input_selector, "")
        for i in range(queryLengthLimit):
            await page.keyboard.press('Backspace')
        await page.type(input_selector, query)
        await page.keyboard.press('Enter')
        logging.info(f"完成 query = '{query}' 的搜索")
    
    async def getSearchResult(query_page):
        '''
        获得搜索结果页显示的问题和url
        返回： {question1:url1, question2:url2, ...}
        '''
        qList = await query_page.evaluate(
            '''
            () => {
                const QuestionSegs = document.querySelectorAll(".List-item");
                const questionContents = [];
                QuestionSegs.forEach(
                    question => {
                        const lst = question.querySelectorAll("meta");
                        if (lst.length >= 2) {
                            questionContents.push(
                                {
                                    "question" : lst[1].getAttribute("content"),
                                    "url"      : lst[0].getAttribute("content")
                                }
                            )
                        }
                    }
                );
                return questionContents;
            }
            '''
        )
        return qList
        
        




class PageOperation():
    @staticmethod
    async def scrollDown(page, max_down, downTag=".Button.QuestionAnswers-answerButton"):
        '''
        获取所有回答
        下拉操作, 下拉很多后,需要下拉到底后继续下拉,直到出现新内容,设置个时间,下拉到出现特定符号:"写回答" 则停止
        如果 downTag = None 代表不判断是否到达页面底部，默认值为回答页的页面底部
        '''
        down = None
        num = 0
        while True:
            if down == None and num <=max_down:  # 太大会清除一些
                # 等待刷新时间
                await asyncio.sleep(random.randint(2, 4))
                await page.evaluate('''
                    () => {
                        window.scrollBy(0, 10000);
                        window.scrollBy(0, -1000)
                    }
                ''')
                # 判断是否到达网页底部
                if downTag != None:
                    down = await page.querySelector(downTag)
                num += 1
                logging.info(f"下拉第 {num} 次")
                # if num % 10 == 0:
                    # logging.info(f"下拉第 {num} 次保存了一次屏幕截图")
                    # await page.screenshot({'path' : f'{filename}-{num}.png'})
            else:
                if down != None:
                    logging.info(f"下拉第 {num} 次完成所有数据的请求")
                else:
                    logging.info(f"下拉达到第 {num} 次")
                break
        
        # 完成最后一次下拉的加载
        await asyncio.sleep(random.randint(3, 4))
        # 到底后额外尝试 3 次下拉,以加载完成
        for i in range(3):
            await page.evaluate('''
                () => {
                    window.scrollBy(0, 10000);
                    window.scrollBy(0, -5000);
                }
            ''')  
            await asyncio.sleep(random.randint(3, 4))  

        # 等待最后一次下拉完成网页渲染,如果不等待,则由于未渲染完成,导致网页新更新的数据无法通过设置的CSS路径访问
        await asyncio.sleep(random.randint(3, 4))
        
        if down != None:
            return True  # 该次下拉未使得页面覆盖所有数据
        else:
            return False # 该次下拉未使得页面覆盖所有数据


    @staticmethod
    async def isClickQuestionMore(page) -> bool:
        """
        实现点击问题全部
        return 
        是否成功点击"显示全部"
        """
        try:
            await page.click('.Button.QuestionRichText-more')
            return True
        except PageError as PError:
            # 有时候没有点击更多的选项
            logging.info(f"Question : {PageError}")
            return False


    @staticmethod
    async def isRobotVerify(page) -> bool:
        verify_exist1 = await page.evaluate("document.querySelector('.Unhuman-verificationCode') != null")
        verify_exist2 = await page.evaluate("document.querySelector('title').text.contains('安全验证')")
        return (verify_exist1 or verify_exist2)
        

class QuestionCrawler():
    
    @staticmethod
    async def questionContentCrawl(page)->dict:
        
        # 点击问题全部
        await PageOperation.isClickQuestionMore(page)
        
        question_content = await page.evaluate('''
            () => {
                const mainElement = document.querySelector(".QuestionHeader");
                const titleElement = mainElement.querySelector(".QuestionHeader-title");
                const authorElement = mainElement.querySelector(".QuestionAuthor .css-1gomreu .UserLink-link");
                
                let authorURL = null;
                let authorName = null;
                
                if (authorElement) {
                    authorURL = authorElement.href;
                    authorName = authorElement.querySelector("img").alt;
                }   
                
                const title = titleElement.textContent;
                const qContentElement = mainElement.querySelector(".RichText.ztext.css-117anjg");
                
                let qContent = null;
                
                if (qContentElement) {
                    qContent = qContentElement.innerHTML; // 由于格式不统一, 不进行提取, 后面用beautifulsoup进行文本的提取
                }
                
                return {
                    "authorName" : authorName,
                    "authorURL" : authorURL,
                    "title" : title,
                    "QContentHTML" : qContent
                }
            }
        '''
        )
        return question_content
    
    @staticmethod
    async def questionTagCrawl(page):
        parent_selector = '.Tag-content'  # 父节点的选择器

        # tag_dict = {tag1 : href1, tag2 : href2, ...}
        tag_dict = await page.evaluate('''
            (parentSelector) => {
                const parentElements = document.querySelectorAll(parentSelector);
                const contents = {};
                parentElements.forEach(parentElement => {
                    contents[parentElement.textContent] = parentElement.querySelector('a').href
                    
                })
                return contents;
            }
        ''', parent_selector)
        return tag_dict
    
    @staticmethod
    async def numberBoardCrawl(page):
        # 获取关注人数和浏览数
        numberBoard = await page.evaluate('''
            () => {
                const FollowStatusElements = document.querySelectorAll(".NumberBoard-item")
                
                const status = {}
                FollowStatusElements.forEach(
                    followStatus => {
                        const name = followStatus.querySelector(".NumberBoard-itemName").textContent;
                        const num = followStatus.querySelector(".NumberBoard-itemValue").textContent;
                        status[name] = num;     
                    }
                )
                return status
            }        
        '''
        )
        return numberBoard

    
    

class AnswerCrawler():
    
    @staticmethod
    async def allAnswersTextExtraction(page):
        """
        当网页下拉完成后，进行该网页上所有回答的文本提取
        
        return
        :answersText : [answer_dict1, answer_dict2, answer_dict3, ...]
        """
        answerElements = await page.querySelectorAll(".List-item")
        answersText = []

        for answerElement in answerElements:
            htmlContent = await answerElement.getProperty('outerHTML')
            htmlContentText = await htmlContent.jsonValue()
            attrDict = AnswerCrawler().getOneAnswerAttr(htmlContentText)
            answersText.append(attrDict)
        
        logging.info(f"获得 {len(answerElements)} 条回答")
        
        return answersText

    @staticmethod
    def getOneAnswerAttr(textHTML) -> dict:
        '''
        获得单个回答的文本内容与其他属性
        input:
        textHTML : .List-item 部分的内容
        
        return
        : 某个回答的文本
        '''
        
        bs = BeautifulSoup(textHTML, 'lxml')
        
        # 最后返回的字典
        answer = {
            'username' : None,      # 用户名
            'userURL' : None,       # 用户链接
            'userDetail' : None,    # 用户详细描述
            'releaseTime' : None,   # 文章发布时间
            'editTime' : None,      # 文章编辑时间
            'approvals' : None,     # 文章赞同数
            'comments' : None,      # 文章评论数
            'content' : None,       # 文章内容
        }
        
        # 获得答主的用户名,URL,detail(无则为None)
        UserNameAndURL = bs.select(
            "div.AuthorInfo.AnswerItem-authorInfo.AnswerItem-authorInfo--related > div.AuthorInfo > div > div.AuthorInfo-head > span > div > a")       

        UserProfile = bs.select(
            "div.AuthorInfo.AnswerItem-authorInfo.AnswerItem-authorInfo--related > div.AuthorInfo > div > div.AuthorInfo-detail > div > div")
            
        
        if len(UserNameAndURL) != 0:
            answer['username'] = UserNameAndURL[0].text
            try:
                answer['userURL'] = UserNameAndURL[0]['href']
            except:
                logging.error(f"getAnswerAttr : can not find user's url in [{textHTML}]") 
        else:
            logging.error(f"getAnswerAttr : can not find username and url in [{textHTML}]") 
        
        if len(UserProfile) != 0:
            answer['userDetail'] = UserProfile[0].text
        else:
            logging.info("getAnswerAttr : There is no detail description of the user")
        
        # 获得文章的发布和最新的编辑时间
        tag = False
        try:
            times = bs.select(
                "div.RichContent.RichContent--unescapable > div:nth-child(2) > div.ContentItem-time > a > span")
            releaseTime = times[0]['aria-label']
            editTime = times[0].text
            tag = True
        except:
            logging.error(f"getAnswerAttr : can not find the release and edit time in [{textHTML}]")
        
        if tag :
            try:
                releaseTime = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', releaseTime).group()
                editTime = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', editTime).group()
                answer['releaseTime'] = releaseTime
                answer['editTime'] = editTime
            except AttributeError as AError:
                logging.error(f'getAnswerAttr : {AError} : The regular expression can not extract time')
            except:
                logging.error(f'getAnswerAttr : Unkown Error , can not get releaseTime or editTime in [{textHTML}]')
        
        # 获得文章的赞同数和评论数
        try:
            supports = bs.find("div", {'class':'ContentItem-actions'}).find('button')['aria-label']
            supports = supports.replace("\u200b", "")
            # supports = re.search(r"\d+\.\d+|\d+", supports).group() # 认为知乎上没有超过10万点赞的，超过则显示
        except AttributeError as AError:
            supports = None
            logging.error(f"getAnswerAttr : can not locate the approvals in {textHTML}")
        except:
            supports = None
            logging.error(f"getAnswerAttr : other errors occur when try to get the supports in {textHTML}")
        
        
        try:
            comments = bs.select("div.ContentItem-actions > button:nth-child(2)")
            comments = comments[0].text.replace("\u200b", "")
        except AttributeError as AError:
            comments = None
            logging.error(f"getAnswerAttr : can not locate the comments in {textHTML}")
        except:
            comments = None
            logging.error(f"getAnswerAttr : other errors occur when try to get the comments in {textHTML}")
        
        answer['approvals'] = supports
        answer['comments'] = comments
        
        
        # 获得文章的内容(有部分文字在h3里面没有爬取)
        try:
            content = bs.select("div.RichContent.RichContent--unescapable > span:nth-child(1) > div > div > span")
            # 新增
            # 其实将 findAll 的 recursive 设置为False,然后搜索['p'. 'h2', 'h3', 'ol' ,'ul', 'blockquote', 'code', 'table'],
            # 然后再对每一种数据类型进行细化的处理会更好,把他们作为一个一个对象进行处理会更好
            taget_label= ['p', 'h2', 'h3', 'li', 'blockquote', 'code', 'table']
            contentList =  content[0].findAll(taget_label)  # (有部分文字在h3里面没有爬取) 后面需要改进,注意知乎的markdown格式所起的作用
        except IndexError as IError:
            logging.error(f"{IError} : can not get content of answer in {textHTML}")
            contentList = None
        except:
            contentList = None
            logging.error(f"other errors occur when locate the content of answer in {textHTML}")
        clearedContentList = []
        # 获取文本内容, 空的部分对应换行
        if contentList != None:
            for c in contentList:
                clearedContentList.append(c.text)
        
        answer['content'] = clearedContentList
        
        return answer  
        