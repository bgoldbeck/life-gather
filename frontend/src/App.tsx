import { useCallback, useEffect, useState } from 'react'
import {
  Activity,
  ArrowLeft,
  ArrowUpRight,
  BookOpen,
  Boxes,
  Camera,
  CircleCheck,
  ClipboardCheck,
  FileText,
  House,
  LayoutDashboard,
  Leaf,
  LockKeyhole,
  MailSearch,
  MessageCircle,
  Network,
  Receipt,
  Settings,
  ShieldCheck,
  Sparkles,
  Wrench,
  Zap,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { AuthGate } from './AuthGate'
import { PrivateSettingsPanel } from './PrivateSettingsPanel'
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
import type { ReconnectTarget } from './reconnect'
import { GlobalSearch, type SearchResult } from './GlobalSearch'
import type { Theme } from './appearance'
import { ToneIcon } from './tones'

const navigation = [
  {
    name: 'Power Center',
    icon: Zap,
    tone: 'power',
    description: 'Capabilities, health and useful next actions.',
  },
  {
    name: 'Photos',
    icon: Camera,
    tone: 'photos',
    description: 'Private receipt and nameplate photos.',
  },
  {
    name: 'Documents',
    icon: FileText,
    tone: 'documents',
    description: 'Private PDF evidence and reviewed text.',
  },
  {
    name: 'Review',
    icon: ClipboardCheck,
    tone: 'power',
    description: 'Review pending item details and uncertain identity matches.',
  },
  {
    name: 'Scans',
    icon: MailSearch,
    tone: 'email',
    description: 'Private requested and scheduled imports.',
  },
  {
    name: 'Purchases',
    icon: Receipt,
    tone: 'finance',
    description: 'Reconcile order, receipt, shipment and payment evidence.',
  },
  {
    name: 'Profiles',
    icon: House,
    tone: 'graph',
    description: 'Sourced home and vehicle details.',
  },
  {
    name: 'Maintenance',
    icon: Wrench,
    tone: 'maintenance',
    description: 'Your stated tasks, due dates and completion history.',
  },
  { name: 'Overview', icon: LayoutDashboard, tone: 'assets', description: '' },
  {
    name: 'Assets',
    icon: Boxes,
    tone: 'assets',
    description:
      'A home for the things you own, their history, and their documents.',
  },
  {
    name: 'Memories',
    icon: BookOpen,
    tone: 'ai',
    description: 'Explore your original sources and the memories they support.',
  },
  {
    name: 'Graph',
    icon: Network,
    tone: 'graph',
    description: 'Explore the connections between people, places, and things.',
  },
  {
    name: 'Settings',
    icon: Settings,
    tone: 'settings',
    description: 'Manage privacy, authentication, and model connections.',
  },
  {
    name: 'Operations',
    icon: Activity,
    tone: 'settings',
    description: 'Installation health: background jobs, problems and storage.',
  },
] as const

type View = (typeof navigation)[number]['name']

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
          userId={userId}
          expandSignal={expandAssistant}
          page={
            <main id="main-content" className="main-content" data-view={view}>
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
                <>
                  <div className="section-label">
                    <span /> A HOME FOR WHAT MATTERS
                  </div>
                  <section className="welcome">
                    <div className="welcome-copy">
                      <h1>
                        A little less <br />
                        to remember.
                      </h1>
                      <p>
                        Life is full of details. Give them a place to belong.
                        <br className="desktop-break" /> Your things, stories,
                        and connections — with their sources intact.
                      </p>
                      <Button
                        className="explore-button"
                        onClick={() => {
                          setReceiptSourceId('')
                          openAssistant()
                        }}
                      >
                        Explore your workspace{' '}
                        <ArrowUpRight aria-hidden="true" size={17} />
                      </Button>
                      <span className="preview-note">
                        Your account is ready. Save a memory or find it in Chat.
                      </span>
                    </div>
                    <div className="memory-illustration" aria-hidden="true">
                      <div className="orbit orbit-one" />
                      <div className="orbit orbit-two" />
                      <div className="graph-line line-one" />
                      <div className="graph-line line-two" />
                      <div className="graph-line line-three" />
                      <div className="graph-center">
                        <Leaf size={47} strokeWidth={1.4} />
                      </div>
                      <span
                        className="graph-node node-one"
                        data-tone="documents"
                      >
                        <BookOpen size={22} />
                      </span>
                      <span className="graph-node node-two" data-tone="assets">
                        <Boxes size={22} />
                      </span>
                      <span className="graph-node node-three" data-tone="ai">
                        <MessageCircle size={22} />
                      </span>
                      <span className="little-node little-one" />
                      <span className="little-node little-two" />
                      <span className="illustration-caption">
                        Every detail has a connection.
                      </span>
                    </div>
                  </section>
                  <section
                    className="start-section"
                    aria-labelledby="start-heading"
                  >
                    <div className="section-heading">
                      <h2 id="start-heading">Your story starts here</h2>
                      <Badge variant="secondary">In the making</Badge>
                    </div>
                    <p className="section-description">
                      A thoughtful foundation for memories you can trust.
                    </p>
                    <div className="feature-grid">
                      {[
                        {
                          icon: MessageCircle,
                          tone: 'ai',
                          title: 'Start with a conversation',
                          text: 'A natural way to capture a detail or find something you remember.',
                          target: 'Assistant' as const,
                          label: 'Explore Chat',
                        },
                        {
                          icon: Boxes,
                          tone: 'assets',
                          title: 'Keep the whole story',
                          text: 'Connect your belongings to their receipts, repairs, and history.',
                          target: 'Assets' as View,
                          label: 'Explore Assets',
                        },
                        {
                          icon: Network,
                          tone: 'graph',
                          title: 'See how it connects',
                          text: 'Follow the relationships between your memories, people, and places.',
                          target: 'Graph' as View,
                          label: 'Explore Graph',
                        },
                      ].map(
                        ({ icon: Icon, tone, title, text, target, label }) => (
                          <Card key={title} className="feature-card">
                            <CardContent>
                              <span className="feature-icon" data-tone={tone}>
                                <Icon
                                  aria-hidden="true"
                                  size={22}
                                  strokeWidth={1.5}
                                />
                              </span>
                              <h3>{title}</h3>
                              <p>{text}</p>
                              <Button
                                variant="link"
                                className="feature-link"
                                onClick={() =>
                                  target === 'Assistant'
                                    ? openAssistant()
                                    : setView(target)
                                }
                              >
                                {label}
                                <ArrowUpRight aria-hidden="true" size={15} />
                              </Button>
                            </CardContent>
                          </Card>
                        ),
                      )}
                    </div>
                  </section>
                  <div className="principles">
                    <ShieldCheck aria-hidden="true" size={23} />
                    <div>
                      <strong>Your memories deserve a source of truth.</strong>
                      <p>
                        Original evidence preserved. Uncertainty made clear.
                        History kept intact.
                      </p>
                    </div>
                    <span className="principles-icon">
                      <CircleCheck aria-hidden="true" size={20} />
                    </span>
                  </div>
                  <footer className="workspace-footer">
                    Made for a life that keeps growing.
                    <span>
                      <Sparkles aria-hidden="true" size={13} /> LifeGather ·
                      Working name
                    </span>
                  </footer>
                </>
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
