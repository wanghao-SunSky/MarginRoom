"""Small, explicit translations for API and persisted run messages."""
import re

EN = {
    '模型服务在输出过程中报错，请稍后重试。':'The model provider reported a streaming error. Please try again.',
    '模型回复未完整结束，请重试。':'The model response did not finish. Please try again.',
    '资料不存在':'Document not found.',
    '段落不存在':'Section not found.',
    '段落不存在或不属于本书':'Section not found in this document.',
    '单份文件最大 20 MB。':'Each file must be 20 MB or smaller.',
    '这份资料没有 PDF 原文件':'This document has no original PDF file.',
    '记录不存在':'Record not found.',
    '内容已变化，请重新打开后编辑。':'This content has changed. Reopen it before editing.',
    '卡片格式或来源无效':'Invalid card format or source.',
    '模型 API Key 尚未配置。当前可以导入、阅读、做笔记；接入后即可提问。':'A model API key is not configured. You can import, read, and take notes now; configure a key to ask questions.',
    '请求编号已用于另一次提问。':'This request ID was already used for a different question.',
    '这本资料有一条回答正在进行，请先等待或停止。':'A response is already running for this document. Wait or stop it first.',
    '任务不存在':'Run not found.',
    '指令不存在':'Command not found.',
    '指令不属于这个阅读窗口':'This command belongs to another reading window.',
    '目标不属于当前书籍':'The destination is not in the current document.',
    '目标与导航指令不一致':'The destination does not match the navigation command.',
    '页面版本没有前进':'The reading position has not advanced.',
    '接口不存在':'API endpoint not found.',
    '任务已停止，未保存新内容':'The run has stopped. No new content was saved.',
    '来源不属于当前资料':'The source is not in the current document.',
    '这版支持 Markdown、TXT 和 PDF。':'This version supports Markdown, TXT, and PDF files.',
    '文件为空':'The file is empty.',
    '没有可阅读内容':'No readable content was found.',
    '请先解除 PDF 的密码保护再导入。':'Remove password protection from the PDF before importing it.',
    '体验版单份 PDF 最多 600 页，请先拆分。':'PDFs are limited to 600 pages. Split the file before importing it.',
    'PDF 无法解析，请确认文件完整且未加密。':'The PDF could not be parsed. Check that it is complete and unencrypted.',
    '文本需为 UTF-8 编码，请转换后重试。':'Text files must use UTF-8 encoding. Convert the file and try again.',
    '模型服务本次回答超时，已停止等待。已收到的片段会保留，请稍后重试。':'The model service response timed out. Received text is retained. Please try again.',
    '连接模型服务超时，已停止等待，请稍后重试。':'The connection to the model service timed out. Please try again.',
    '与模型服务的连接中断或暂时无法建立，已停止本次回答。请检查网络后重试。':'The connection to the model service was interrupted or could not be established. This response has stopped. Check your connection and try again.',
    '本次已保存的学习记录仍可在笔记或复习卡中查看，无需重新生成。':'Notes or cards already saved in this run remain available in Notes or Cards; you do not need to generate them again.',
    '模型服务密钥无效，请检查服务端配置。':'The model service API key is invalid. Check the server configuration.',
    '模型服务账户余额不足，请在模型服务平台检查余额后重试。':'The model service account has insufficient balance. Check your provider before retrying.',
    '模型服务请求频率受限，请稍后重试。':'The model service rate-limited this request. Please try again later.',
    '模型服务当前繁忙或暂时不可用，已停止本次请求。请稍后重试。':'The model service is busy or temporarily unavailable. This request has stopped; please try again later.',
    '模型服务暂无新内容，等待超时，已停止本次回答。已收到的片段会保留，请稍后重试。':'The model service stopped producing new content. This response timed out; received text is retained. Please try again.',
    '模型混合了回复与操作，已停止；请重试。':'The model mixed a final reply with an operation. This run has stopped; please try again.',
    '回复结构发生变化，已停止；请重试。':'The response format changed unexpectedly. Please try again.',
    '模型服务回答未完整结束，已保留收到的片段，请重试；这次不会被记作完整回答。':'The model service response did not finish. Received text is retained, but this is not saved as a complete answer. Please try again.',
    '回复格式未完整结束，请重试。':'The response format is incomplete. Please try again.',
    '这次阅读任务已达到上下文预算，请缩小范围后继续。':'This reading task reached its context budget. Continue with a narrower question.',
    '回复或引用校验未通过，已保留片段，请重试。':'The reply or its references could not be validated. Received text is retained. Please try again.',
    '模型没有返回可显示的内容，请重试。':'The model returned no displayable content. Please try again.',
    '本次查询步骤较多，已停止；请缩小问题范围。':'This query reached the tool-step limit. Please narrow the question.',
    '工具参数必须为对象':'Tool arguments must be an object.',
    '本次探索达到轮次上限，已保留过程，请缩小范围继续。':'This task reached the model-round limit. The trace is retained; continue with a narrower question.',
    '已停止。本次已保存的产物仍可查看。':'Stopped. Notes and cards already saved remain available.',
    '请求未完成，请检查网络并重试。':'The request did not complete. Check your connection and try again.',
    '服务已重启，这次回答未完成；可以重新提问。':'The server restarted before this answer finished. You can ask again.',
    '这条旧回复的格式或引用不完整，请重新提问。':'This older reply has an incomplete format or reference. Please ask again.',
    '未找到当前书籍的这条历史':'This conversation record was not found in the current document.',
    '无效产物类型':'Invalid artifact type.',
    '内容为空或过长':'Content is empty or too long.',
    '每批需要1到6张卡片':'Each batch must contain one to six cards.',
    '卡片字段错误':'Invalid card fields.',
    '卡片内容为空或过长':'Card content is empty or too long.',
    '未知工具':'Unknown tool.',
    '标题或内容为空':'The title or content is empty.',
    '本次请求已保存同类内容，不能用另一份内容覆盖；请另发请求。':'This run already saved a different item of this type. Start a new request to save another item.',
    '问题不能为空白':'The question cannot be blank.',
}

def tr(message, language='zh'):
    if language!='en' or not isinstance(message,str):return message
    if message in EN:return EN[message]
    match=re.fullmatch(r'模型服务暂时无法完成请求（HTTP (\d+)），请稍后重试。',message)
    if match:return f'The model service could not complete this request (HTTP {match[1]}). Please try again.'
    return message

def request_language(request):
    return getattr(request.state,'language',None) or ('en' if request.query_params.get('language',request.headers.get('x-reading-language','zh'))=='en' else 'zh')
