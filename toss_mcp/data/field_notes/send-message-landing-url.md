---
id: send-message-landing-url
title: send-message 이동 URL 변수
status: undocumented
as_of: 2026-08
related_sources:
  - apps_in_toss
triggers:
  - send-message
  - send message
  - landingUrl
  - landing url
  - 이동 URL
  - 이동 url
  - templateSetCode
  - 기능성 메시지
  - 스마트 발송
  - 스마트 메시지
  - intoss
  - 딥링크
  - 랜딩 URL
  - 알림 클릭
citations:
  - https://techchat-apps-in-toss.toss.im/t/url/3297
  - https://techchat-apps-in-toss.toss.im/t/send-message-api-url/4354
---

# send-message 이동 URL 변수

공식 send-message API 요청 바디에는 `templateSetCode`와 `context`만 있다. `landingUrl` 같은 URL 필드는 없다. 발송 건별 이동 URL은 API에 넣는 값이 아니라, 콘솔 기능성 메시지의 이동 URL에 `{{ 변수 }}`를 넣고 `context`로 치환하는 방식이다.

이 문법은 공식 개발자 문서에 아직 없다. 앱인토스 담당자가 개발자 커뮤니티에서 확인한 내용이며, 콘솔에 `{{ 변수 }}`를 저장할 수 있는지는 저장 전에 다시 확인한다.

## 콘솔에 쓰는 방식

클릭 시 이동할 화면 URL → 특정 화면:

```
intoss://app-name/product/{{ productId }}
```

서버 발송:

```json
{
  "templateSetCode": "product_complete",
  "context": {
    "productId": "123"
  }
}
```

클릭 시 `intoss://app-name/product/123`으로 열린다. 발송 건마다 다른 경로가 필요하면 `intoss://testApp/{{ orderId }}`처럼 경로에 변수를 넣고 `context.orderId`를 전달한다.

## 문법

- 올바른 변수: `{{ productId }}` 또는 `{{productId}}`. `{productId}`가 아니다.
- 앱 이름(`app-name`, `testApp`)은 예약 변수가 아니다. 콘솔에 직접 적는다. `{appName}` 자동 주입이 아니다.
- 제목/본문에 변수를 넣지 않아도 된다. 이동 URL에만 있으면 된다.
- `?productId=123` 같은 쿼리스트링은 푸시/딥링크에서 깨진 사례가 있다. 경로 변수를 쓴다.

댓글 알림처럼 같은 글로 보내면 `postId` 하나만으로 충분하다. 특정 댓글 위치로 스크롤하는 동작은 앱 구현에 달려 있다.

```
intoss://your-app/community-post/{{ postId }}
```

```json
{
  "templateSetCode": "your-app-comment-alert",
  "context": {
    "postId": "12"
  }
}
```
