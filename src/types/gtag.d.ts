declare global {
  interface Window {
    gtag: (
      command: 'config' | 'event' | 'consent',
      targetId: string | Date,
      config?: {
        page_title?: string
        page_location?: string
        utm_source?: string
        utm_medium?: string
        utm_campaign?: string
        send_to?: string
        value?: number
        currency?: string
        transaction_id?: string
        [key: string]: any
      }
    ) => void
  }
}

export {}