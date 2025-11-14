import base64
from logger_conf import logger

def save_pdf(pdf_file: str,file_path:str):
    try:
        with open(file_path, "wb") as f:
            pdf_data = base64.b64decode(pdf_file)  
            f.write(pdf_data)
        logger.info(f"📄 PDF 文件已保存至: {file_path}")
        return True
    except Exception as e:
        logger.error(f"❌ PDF 文件保存失败: {e}")
        raise e    
