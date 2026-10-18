"""Installation-owned mail delivery. Never log message bodies or credentials."""

import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol


class MailSender(Protocol):
    def send(self, recipient: str, subject: str, body: str) -> None: ...


class SmtpSender:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        implicit_tls: bool = False,
    ) -> None:
        self.host, self.port, self.username, self.password = (
            host,
            port,
            username,
            password,
        )
        self.sender, self.implicit_tls = sender, implicit_tls

    def send(self, recipient: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = (
            self.sender,
            recipient,
            subject,
        )
        message.set_content(body)
        context = ssl.create_default_context()
        if self.implicit_tls:
            with smtplib.SMTP_SSL(
                self.host, self.port, timeout=10, context=context
            ) as client:
                client.login(self.username, self.password)
                client.send_message(message)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=10) as client:
                client.ehlo()
                client.starttls(context=context)
                client.ehlo()
                client.login(self.username, self.password)
                client.send_message(message)
