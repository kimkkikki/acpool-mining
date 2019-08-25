import smtplib
from email.mime.text import MIMEText
import os


def send_worker_disconnect_email(to_address, username, worker_name, coin_name):
    msg = MIMEText("""
Hi, {}

Thanks for using ACPool!

Coin : {}
Disconnected Worker : {}

* If you want send reply, mail to acpool@acpool.me

Happy mining!
ACPool
    """.format(username, coin_name, worker_name))
    msg['Subject'] = 'ACPool - Your worker {} is disconnected'.format(worker_name)
    msg['From'] = os.getenv("MAILGUN_SENDER_MAIL")
    msg['To'] = to_address

    smtp = smtplib.SMTP('smtp.mailgun.org', 2525)
    smtp.login(os.getenv("MAILGUN_SENDER_MAIL"), os.getenv("MAILGUN_SENDER_KEY"))
    smtp.sendmail(msg['From'], msg['To'], msg.as_string())
    smtp.quit()
