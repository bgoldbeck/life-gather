import { useCallback, useEffect, useState } from 'react'
import { ArrowLeft, LockKeyhole } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { AuthGate } from './AuthGate'
import { PrivateSettingsPanel } from './PrivateSettingsPanel'
import { SharedFiles } from './SharedFiles'
import { claimShareOnce, readShareRequest } from './shareTarget'
import { PasswordSettings } from './PasswordSettings'
import { AccountDeletion } from './AccountDeletion'
import { StorageUsage } from './StorageUsage'
import { ChatDock } from './ChatDock'
import { NavigationDock } from './NavigationDock'
import { WorkspaceAssistant } from './WorkspaceAssistant'
import { ReviewPanel } from './ReviewPanel'
import { PhotosPanel } from './PhotosPanel'
import { MemoriesPanel } from './MemoriesPanel'
import { AssetsPanel } from './AssetsPanel'
import { BuildInfo, type Build } from './BuildInfo'
import { AppearanceSettings } from './AppearanceSettings'
import { RetentionSettings } from './RetentionSettings'
import { GraphPanel } from './GraphPanel'
import { ProfilesPanel } from './ProfilesPanel'
import { MaintenancePanel } from './MaintenancePanel'
import { DocumentsPanel } from './DocumentsPanel'
import { MailboxesPanel } from './MailboxesPanel'
import { ScansPanel } from './ScansPanel'
import { PurchasesPanel } from './PurchasesPanel'
import { PowerCenter } from './PowerCenter'
import { OperationsPanel } from './OperationsPanel'
import { TimelinePanel } from './TimelinePanel'
import { OverviewPanel } from './OverviewPanel'
import type { ReconnectTarget } from './reconnect'
import { GlobalSearch, type SearchResult } from './GlobalSearch'
import type { Theme } from './appearance'
import { ToneIcon } from './tones'
import { navigation, type View } from './navigation'

export function Workspace({
  userId = '',
  userName,
  userEmail = '',
  onSignOut,
  signingOut = false,
  csrfToken = '',
  refreshSession,
  passwordEnabled = false,
  deliveryEnabled = false,
  build,
  appearance = 'system',
}: {
  userId?: string
  userName?: string
  userEmail?: string
  onSignOut?: () => void
  signingOut?: boolean
  csrfToken?: string
  refreshSession?: () => Promise<void>
  passwordEnabled?: boolean
  deliveryEnabled?: boolean
  build?: Build
  appearance?: Theme
}) {
  const [view, setView] = useState<View>(() =>
    ['connected', 'failed'].includes(
      new URLSearchParams(window.location.search).get('mailbox') ?? '',
    )
      ? 'Settings'
      : 'Overview',
  )
  // Files shared from another Android app arrive as /?share=<id>; the address is
  // cleaned at once so reloading never asks the service worker for them again.
  const [share, setShare] = useState(() =>
    readShareRequest(window.location.search),
  )
  useEffect(() => {
    if (!share) return
    const url = new URL(window.location.href)
    url.searchParams.delete('share')
    url.searchParams.delete('more')
    window.history.replaceState(window.history.state, '', url)
  }, [share])
  const [graphEntityId, setGraphEntityId] = useState('')
  const [assetId, setAssetId] = useState('')
  const [profileId, setProfileId] = useState('')
  const [receiptSourceId, setReceiptSourceId] = useState('')
  const [scanRunId, setScanRunId] = useState('')
  const [reconnectKey, setReconnectKey] = useState<ReconnectTarget | null>(null)
  // An AI key's Reconnect opens its Replace form; Gmail goes straight to Google.
  const openReconnect = (target: ReconnectTarget) => {
    setReconnectKey({ ...target })
    setView('Settings')
  }
  // A photo, document or source to open on its page; `visit` remounts the page.
  const [target, setTarget] = useState({
    photo: '',
    document: '',
    source: '',
    visit: 0,
  })
  const [expandAssistant, setExpandAssistant] = useState(0)
  // Operations is listed only for accounts the installation names as operators.
  const [operator, setOperator] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/operator/access', {
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal,
    })
      .then((response) => (response.ok ? response.json() : null))
      .then((data: { operator?: boolean } | null) => {
        if (!controller.signal.aborted) setOperator(data?.operator === true)
      })
      .catch(() => undefined)
    return () => controller.abort()
  }, [userId])
  const [contextRevision, setContextRevision] = useState(0)
  const [powerRevision, setPowerRevision] = useState(0)
  const powerChanged = () => setPowerRevision((value) => value + 1)
  const [record, setRecord] = useState<{
    page: View
    id: string | null
    revision: number
  }>({ page: 'Overview', id: null, revision: 0 })
  const assetContext = useCallback(
    (id: string | null) =>
      setRecord((previous) => ({
        page: 'Assets',
        id,
        revision: previous.revision + 1,
      })),
    [],
  )
  const profileContext = useCallback(
    (id: string | null) =>
      setRecord((previous) => ({
        page: 'Profiles',
        id,
        revision: previous.revision + 1,
      })),
    [],
  )
  const graphContext = useCallback(
    (id: string | null) =>
      setRecord((previous) => ({
        page: 'Graph',
        id,
        revision: previous.revision + 1,
      })),
    [],
  )
  const openAssistant = () => setExpandAssistant((value) => value + 1)
  const openAsset = (id: string) => {
    setAssetId(id)
    setView('Assets')
  }
  const openTarget = (page: View, opened: Partial<typeof target>) => {
    setTarget((previous) => ({
      photo: '',
      document: '',
      source: '',
      ...opened,
      visit: previous.visit + 1,
    }))
    setView(page)
  }
  const openResult = (result: SearchResult) => {
    if (result.kind === 'asset') openAsset(result.id)
    else if (result.kind === 'record') {
      setGraphEntityId(result.id)
      setView('Graph')
    } else if (result.kind === 'photo')
      openTarget('Photos', { photo: result.id })
    else if (result.kind === 'document')
      openTarget('Documents', { document: result.id })
    else if (result.photo_id) openTarget('Photos', { photo: result.photo_id })
    else if (result.document_id)
      openTarget('Documents', { document: result.document_id })
    else openTarget('Memories', { source: result.id })
  }
  const current = navigation.find((item) => item.name === view)!

  return (
    <NavigationDock
      userId={userId}
      navigation={
        <>
          <div className="brand">
            <img
              className="brand-mark"
              src="/brand/lifegather-icon.png"
              width="40"
              height="40"
              alt=""
              aria-hidden="true"
            />
            LifeGather<span className="brand-dot">.</span>
          </div>
          <p className="sidebar-caption">A little more connected.</p>
          <nav aria-label="Main navigation">
            {navigation
              .filter(({ name }) => operator || name !== 'Operations')
              .map(({ name, icon, tone }) => (
                <Button
                  key={name}
                  variant="ghost"
                  className="nav-button"
                  title={name}
                  data-tone={tone}
                  aria-current={view === name ? 'page' : undefined}
                  onClick={() => {
                    if (name === 'Scans') setScanRunId('')
                    setTarget((previous) => ({
                      photo: '',
                      document: '',
                      source: '',
                      visit: previous.visit + 1,
                    }))
                    setView(name)
                  }}
                >
                  <ToneIcon icon={icon} tone={tone} size={15} />
                  <span className="nav-label">{name}</span>
                </Button>
              ))}
          </nav>
          <div className="sidebar-note">
            <LockKeyhole aria-hidden="true" size={18} />
            <div>
              <strong>Built for your own space</strong>
              <p>
                Private by design.
                <br />
                Yours to self-host.
              </p>
            </div>
          </div>
        </>
      }
    >
      <div className="workspace">
        <header className="topbar">
          <span>
            Your personal space <span className="breadcrumb">/ {view}</span>
          </span>
          <GlobalSearch onOpen={openResult} refreshSession={refreshSession} />
          <div className="account-actions">
            <BuildInfo build={build} />
            <span>{userName}</span>
            {onSignOut && (
              <Button
                variant="outline"
                onClick={onSignOut}
                disabled={signingOut}
              >
                {signingOut ? 'Signing out…' : 'Sign out'}
              </Button>
            )}
          </div>
        </header>
        <ChatDock
          defaultCollapsed
          userId={userId}
          expandSignal={expandAssistant}
          page={
            <main id="main-content" className="main-content" data-view={view}>
              {share && (
                <SharedFiles
                  share={share}
                  csrfToken={csrfToken}
                  refreshSession={refreshSession}
                  onClose={() => setShare(null)}
                  onOpenPhotos={() => {
                    setShare(null)
                    openTarget('Photos', {})
                  }}
                  onOpenDocuments={() => {
                    setShare(null)
                    openTarget('Documents', {})
                  }}
                />
              )}
              {view === 'Settings' ? (
                <>
                  <PowerCenter
                    compact
                    userId={userId}
                    changeSignal={powerRevision}
                    onNavigate={setView}
                    onOpenAssistant={openAssistant}
                    refreshSession={refreshSession}
                    csrfToken={csrfToken}
                    onReconnectKey={openReconnect}
                  />
                  <AppearanceSettings
                    theme={appearance}
                    csrfToken={csrfToken}
                    refreshSession={refreshSession}
                  />
                  <RetentionSettings
                    csrfToken={csrfToken}
                    refreshSession={refreshSession}
                  />
                  <StorageUsage refreshSession={refreshSession} />
                  <PrivateSettingsPanel
                    reconnect={reconnectKey}
                    onChanged={powerChanged}
                    csrfToken={csrfToken}
                    refreshSession={refreshSession}
                  />
                  <MailboxesPanel
                    csrfToken={csrfToken}
                    onChanged={powerChanged}
                  />
                  <PasswordSettings
                    configured={passwordEnabled}
                    deliveryEnabled={deliveryEnabled}
                    csrfToken={csrfToken}
                    refreshSession={refreshSession}
                  />
                  <AccountDeletion
                    email={userEmail}
                    passwordEnabled={passwordEnabled}
                    csrfToken={csrfToken}
                    refreshSession={refreshSession}
                  />
                </>
              ) : view === 'Operations' ? (
                <OperationsPanel refreshSession={refreshSession} />
              ) : view === 'Power Center' ? (
                <PowerCenter
                  userId={userId}
                  onNavigate={setView}
                  refreshSession={refreshSession}
                  onOpenAssistant={openAssistant}
                  csrfToken={csrfToken}
                  onReconnectKey={openReconnect}
                  onOpenScan={(id) => {
                    setScanRunId(id)
                    setView('Scans')
                  }}
                />
              ) : view === 'Review' ? (
                <ReviewPanel csrfToken={csrfToken} />
              ) : view === 'Scans' ? (
                <ScansPanel
                  key={scanRunId}
                  csrfToken={csrfToken}
                  onNavigate={setView}
                  onReconnectKey={openReconnect}
                  initialRunId={scanRunId}
                />
              ) : view === 'Timeline' ? (
                <TimelinePanel
                  refreshSession={refreshSession}
                  onOpen={({ view: page, id }) => {
                    if (page === 'Assets') openAsset(id)
                    else if (page === 'Profiles') {
                      setProfileId(id)
                      setView('Profiles')
                    } else if (page === 'Memories')
                      openTarget('Memories', { source: id })
                    else if (page === 'Documents')
                      openTarget('Documents', { document: id })
                    else if (page === 'Photos')
                      openTarget('Photos', { photo: id })
                    else setView(page)
                  }}
                />
              ) : view === 'Purchases' ? (
                <PurchasesPanel
                  csrfToken={csrfToken}
                  onOpenGraph={(id) => {
                    setGraphEntityId(id)
                    setView('Graph')
                  }}
                />
              ) : view === 'Documents' ? (
                <DocumentsPanel
                  key={target.visit}
                  csrfToken={csrfToken}
                  refreshSession={refreshSession}
                  initialDocumentId={target.document}
                />
              ) : view === 'Photos' ? (
                <PhotosPanel
                  key={target.visit}
                  csrfToken={csrfToken}
                  initialPhotoId={target.photo}
                  onOpenAsset={openAsset}
                />
              ) : view === 'Profiles' ? (
                <ProfilesPanel
                  key={profileId}
                  initialEntityId={profileId}
                  onContext={profileContext}
                  contextRevision={contextRevision}
                  csrfToken={csrfToken}
                  refreshSession={refreshSession}
                  onOpenGraph={(id) => {
                    setGraphEntityId(id)
                    setView('Graph')
                  }}
                />
              ) : view === 'Maintenance' ? (
                <MaintenancePanel
                  contextRevision={contextRevision}
                  csrfToken={csrfToken}
                  refreshSession={refreshSession}
                  onOpenProfile={(id) => {
                    setProfileId(id)
                    setView('Profiles')
                  }}
                  onOpenGraph={(id) => {
                    setGraphEntityId(id)
                    setView('Graph')
                  }}
                />
              ) : view === 'Graph' ? (
                <GraphPanel
                  key={graphEntityId}
                  onContext={graphContext}
                  contextRevision={contextRevision}
                  csrfToken={csrfToken}
                  refreshSession={refreshSession}
                  initialEntityId={graphEntityId}
                  onOpenAsset={(id) => {
                    setAssetId(id)
                    setView('Assets')
                  }}
                />
              ) : view === 'Memories' ? (
                <MemoriesPanel
                  key={target.visit}
                  initialSourceId={target.source}
                  onProposeReceipt={(id) => {
                    setReceiptSourceId(id)
                    openAssistant()
                  }}
                  csrfToken={csrfToken}
                  refreshSession={refreshSession}
                />
              ) : view === 'Assets' ? (
                <AssetsPanel
                  onContext={assetContext}
                  contextRevision={contextRevision}
                  initialAssetId={assetId}
                  onOpenGraph={(id) => {
                    setGraphEntityId(id)
                    setView('Graph')
                  }}
                  refreshSession={refreshSession}
                  csrfToken={csrfToken}
                />
              ) : view === 'Overview' ? (
                <OverviewPanel
                  refreshSession={refreshSession}
                  onNavigate={setView}
                  onOpenAssistant={() => {
                    setReceiptSourceId('')
                    openAssistant()
                  }}
                  onOpen={({ view: page, id }) => {
                    if (page === 'Assets') openAsset(id)
                    else if (page === 'Profiles') {
                      setProfileId(id)
                      setView('Profiles')
                    } else if (page === 'Documents')
                      openTarget('Documents', { document: id })
                    else if (page === 'Photos')
                      openTarget('Photos', { photo: id })
                    else setView(page)
                  }}
                />
              ) : (
                <section className="placeholder-view">
                  <Badge variant="secondary">Planned feature</Badge>
                  <current.icon
                    aria-hidden="true"
                    className="placeholder-icon"
                    data-tone={current.tone}
                    size={40}
                    strokeWidth={1.3}
                  />
                  <h1>{view}</h1>
                  <p>{current.description}</p>
                  <div className="placeholder-notice">
                    <strong>{view} is not available yet.</strong>
                    <p>
                      Your workspace is ready. Personal memory storage and this
                      feature will be added in a later milestone.
                    </p>
                  </div>
                  <Button variant="outline" onClick={() => setView('Overview')}>
                    <ArrowLeft aria-hidden="true" size={16} />
                    Back to overview
                  </Button>
                </section>
              )}
            </main>
          }
        >
          <WorkspaceAssistant
            page={view}
            entityId={record.page === view ? record.id : null}
            revision={contextRevision + expandAssistant + record.revision}
            csrfToken={csrfToken}
            refreshSession={refreshSession}
            initialReceiptSourceId={receiptSourceId}
            onOpenAsset={(id) => {
              setAssetId(id)
              setView('Assets')
            }}
            onOpenMaintenance={(id) => {
              setProfileId(id)
              setView('Profiles')
            }}
            onOpenGraph={(id) => {
              setGraphEntityId(id)
              setView('Graph')
            }}
            onOpenScan={(id) => {
              setScanRunId(id)
              setView('Scans')
            }}
            onReconnectKey={openReconnect}
            onRecordChanged={(id) => {
              if (view === 'Assets') setAssetId(id)
              setContextRevision((value) => value + 1)
            }}
          />
        </ChatDock>
      </div>
    </NavigationDock>
  )
}

export default function App() {
  useState(() => {
    const share = readShareRequest(window.location.search)
    if (share) void claimShareOnce(share.id)
  })
  return (
    <AuthGate>
      {(
        user,
        signOut,
        busy,
        csrfToken,
        refreshSession,
        passwordEnabled,
        deliveryEnabled,
        build,
        appearance,
      ) => (
        <Workspace
          key={user.id}
          userId={user.id}
          userName={user.name || user.email}
          userEmail={user.email}
          onSignOut={signOut}
          signingOut={busy}
          passwordEnabled={passwordEnabled}
          deliveryEnabled={deliveryEnabled}
          build={build}
          appearance={appearance}
          csrfToken={csrfToken}
          refreshSession={refreshSession}
        />
      )}
    </AuthGate>
  )
}
