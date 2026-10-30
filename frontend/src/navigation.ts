import {
  Activity,
  BookOpen,
  Boxes,
  Camera,
  ChartColumn,
  ClipboardCheck,
  FileText,
  House,
  LayoutDashboard,
  MailSearch,
  Network,
  Receipt,
  Settings,
  Wrench,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import type { Tone } from './tones'

// The main menu. Other places that link to a page (such as the Overview hero)
// take its icon and tone from here, so they always match the menu.
export const navigation = [
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
    name: 'Timeline',
    icon: ChartColumn,
    tone: 'finance',
    description: 'Spending, activity and events, month by month.',
  },
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
] as const satisfies readonly {
  name: string
  icon: LucideIcon
  tone: Tone
  description: string
}[]

export type View = (typeof navigation)[number]['name']

export function navItem(name: View) {
  return navigation.find((item) => item.name === name)!
}
