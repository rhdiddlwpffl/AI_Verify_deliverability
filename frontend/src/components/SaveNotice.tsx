import { RETENTION_DAYS, type SaveStatus } from '../api/types'

// 저장을 요청한 분석의 저장 결과 안내. 저장이 실패해도 분석 결과는 정상이라는 점을 분명히 한다.
export function SaveNotice({ status }: { status: SaveStatus }) {
  switch (status) {
    case 'saved':
      return (
        <p role="status" className="save-notice">
          ✅ 내 기록에 저장했습니다. &apos;내 기록&apos; 탭에서 볼 수 있고 {RETENTION_DAYS}일 후 자동 삭제됩니다.
        </p>
      )
    case 'failed':
      return (
        <p role="status" className="save-notice save-notice--warn">
          ⚠️ 서버 문제로 기록에 저장하지 못했습니다. 분석 결과는 정상이며, 이 화면에서만 볼 수 있습니다.
        </p>
      )
    case 'no_token':
      return (
        <p role="status" className="save-notice save-notice--warn">
          ⚠️ 이 브라우저에서 기록 식별 정보를 만들지 못해 저장하지 못했습니다. 분석 결과는 정상입니다.
        </p>
      )
    default:
      return null
  }
}
