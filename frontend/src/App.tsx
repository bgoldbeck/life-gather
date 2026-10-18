import { useState } from 'react'
import {
  ArrowLeft,
  ArrowUpRight,
  BookOpen,
  Boxes,
  CircleCheck,
  GitFork,
  LayoutDashboard,
  Leaf,
  LockKeyhole,
  MessageCircle,
  Settings,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { AuthGate } from './AuthGate'
import { PrivateSettingsPanel } from './PrivateSettingsPanel'
import { PasswordSettings } from './PasswordSettings'
import { ChatPanel } from './ChatPanel'
import { AssetsPanel } from './AssetsPanel'
import { BuildInfo, type Build } from './BuildInfo'

const navigation = [
  {
    name: 'Chat',
    icon: MessageCircle,
    description: 'Ask questions and save memories through conversation.',
  },
  { name: 'Overview', icon: LayoutDashboard, description: '' },
  {
    name: 'Assets',
    icon: Boxes,
    description:
      'A home for the things you own, their history, and their documents.',
  },
  {
    name: 'Memories',
    icon: BookOpen,
    description: 'Explore your original sources and the memories they support.',
  },
  {
    name: 'Graph',
    icon: GitFork,
    description: 'Explore the connections between people, places, and things.',
  },
  {
    name: 'Settings',
    icon: Settings,
    description: 'Manage privacy, authentication, and model connections.',
  },
] as const

type View = (typeof navigation)[number]['name']

export function Workspace({
  userName,
  onSignOut,
  signingOut = false,
  csrfToken = '',
  refreshSession,
  passwordEnabled = false,
  deliveryEnabled = false,
  build,
}: {
  userName?: string
  onSignOut?: () => void
  signingOut?: boolean
  csrfToken?: string
  refreshSession?: () => Promise<void>
  passwordEnabled?: boolean
  deliveryEnabled?: boolean
  build?: Build
}) {
  const [view, setView] = useState<View>('Overview')
  const current = navigation.find((item) => item.name === view)!

  return (
    <div className="app-layout">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <aside className="sidebar">
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
          {navigation.map(({ name, icon: Icon }) => (
            <Button
              key={name}
              variant="ghost"
              className="nav-button"
              aria-current={view === name ? 'page' : undefined}
              onClick={() => setView(name)}
            >
              <Icon aria-hidden="true" size={18} />
              <span>{name}</span>
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
      </aside>

      <div className="workspace">
        <header className="topbar">
          <span>
            Your personal space <span className="breadcrumb">/ {view}</span>
          </span>
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
        <main id="main-content" className="main-content">
          {view === 'Settings' ? (
            <>
              <PrivateSettingsPanel
                csrfToken={csrfToken}
                refreshSession={refreshSession}
              />
              <PasswordSettings
                configured={passwordEnabled}
                deliveryEnabled={deliveryEnabled}
                csrfToken={csrfToken}
                refreshSession={refreshSession}
              />
            </>
          ) : view === 'Chat' ? (
            <ChatPanel csrfToken={csrfToken} refreshSession={refreshSession} />
          ) : view === 'Assets' ? (
            <AssetsPanel refreshSession={refreshSession} />
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
                    <br className="desktop-break" /> Your things, stories, and
                    connections — with their sources intact.
                  </p>
                  <Button
                    className="explore-button"
                    onClick={() => setView('Chat')}
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
                  <span className="graph-node node-one">
                    <BookOpen size={22} />
                  </span>
                  <span className="graph-node node-two">
                    <Boxes size={22} />
                  </span>
                  <span className="graph-node node-three">
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
                      title: 'Start with a conversation',
                      text: 'A natural way to capture a detail or find something you remember.',
                      target: 'Chat' as View,
                      label: 'Explore Chat',
                    },
                    {
                      icon: Boxes,
                      title: 'Keep the whole story',
                      text: 'Connect your belongings to their receipts, repairs, and history.',
                      target: 'Assets' as View,
                      label: 'Explore Assets',
                    },
                    {
                      icon: GitFork,
                      title: 'See how it connects',
                      text: 'Follow the relationships between your memories, people, and places.',
                      target: 'Graph' as View,
                      label: 'Explore Graph',
                    },
                  ].map(({ icon: Icon, title, text, target, label }) => (
                    <Card key={title} className="feature-card">
                      <CardContent>
                        <span className="feature-icon">
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
                          onClick={() => setView(target)}
                        >
                          {label}
                          <ArrowUpRight aria-hidden="true" size={15} />
                        </Button>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </section>
              <div className="principles">
                <ShieldCheck aria-hidden="true" size={23} />
                <div>
                  <strong>Your memories deserve a source of truth.</strong>
                  <p>
                    Original evidence preserved. Uncertainty made clear. History
                    kept intact.
                  </p>
                </div>
                <span className="principles-icon">
                  <CircleCheck aria-hidden="true" size={20} />
                </span>
              </div>
              <footer className="workspace-footer">
                Made for a life that keeps growing.
                <span>
                  <Sparkles aria-hidden="true" size={13} /> LifeGather · Working
                  name
                </span>
              </footer>
            </>
          ) : (
            <section className="placeholder-view">
              <Badge variant="secondary">Planned feature</Badge>
              <current.icon
                aria-hidden="true"
                className="placeholder-icon"
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
      </div>
    </div>
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
      ) => (
        <Workspace
          key={user.id}
          userName={user.name || user.email}
          onSignOut={signOut}
          signingOut={busy}
          passwordEnabled={passwordEnabled}
          deliveryEnabled={deliveryEnabled}
          build={build}
          csrfToken={csrfToken}
          refreshSession={refreshSession}
        />
      )}
    </AuthGate>
  )
}
