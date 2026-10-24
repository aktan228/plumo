import { PlumoIcon } from "@/components/ui/plumo-icon";
import Logout01Icon from "@hugeicons/core-free-icons/Logout01Icon";
import SidebarLeft01Icon from "@hugeicons/core-free-icons/SidebarLeft01Icon";
import Chatting01Icon from "@hugeicons/core-free-icons/Chatting01Icon";
import ArrowLeft01Icon from "@hugeicons/core-free-icons/ArrowLeft01Icon";
import Search01Icon from "@hugeicons/core-free-icons/Search01Icon";
import SentIcon from "@hugeicons/core-free-icons/SentIcon";
import UserIcon from "@hugeicons/core-free-icons/UserIcon";
import Cancel01Icon from "@hugeicons/core-free-icons/Cancel01Icon";
import Menu01Icon from "@hugeicons/core-free-icons/Menu01Icon";
import PlugSocketIcon from "@hugeicons/core-free-icons/PlugSocketIcon";
import Tick02Icon from "@hugeicons/core-free-icons/Tick02Icon";
import Book02Icon from "@hugeicons/core-free-icons/Book02Icon";
import TestTube01Icon from "@hugeicons/core-free-icons/TestTube01Icon";
import Edit02Icon from "@hugeicons/core-free-icons/Edit02Icon";
import Megaphone01Icon from "@hugeicons/core-free-icons/Megaphone01Icon";
import FlashIcon from "@hugeicons/core-free-icons/FlashIcon";
import Settings01Icon from "@hugeicons/core-free-icons/Settings01Icon";
import Analytics01Icon from "@hugeicons/core-free-icons/Analytics01Icon";
import UserGroupIcon from "@hugeicons/core-free-icons/UserGroupIcon";
import Share08Icon from "@hugeicons/core-free-icons/Share08Icon";
import PuzzleIcon from "@hugeicons/core-free-icons/PuzzleIcon";
import Wrench01Icon from "@hugeicons/core-free-icons/Wrench01Icon";
import Call02Icon from "@hugeicons/core-free-icons/Call02Icon";
import HelpCircleIcon from "@hugeicons/core-free-icons/HelpCircleIcon";
import ArrowDown01Icon from "@hugeicons/core-free-icons/ArrowDown01Icon";
import Calendar03Icon from "@hugeicons/core-free-icons/Calendar03Icon";
import FilterHorizontalIcon from "@hugeicons/core-free-icons/FilterHorizontalIcon";
import AddCircleIcon from "@hugeicons/core-free-icons/AddCircleIcon";
import GitBranchIcon from "@hugeicons/core-free-icons/GitBranchIcon";
import PaintBoardIcon from "@hugeicons/core-free-icons/PaintBoardIcon";
import UserAdd01Icon from "@hugeicons/core-free-icons/UserAdd01Icon";
import DashboardSquare01Icon from "@hugeicons/core-free-icons/DashboardSquare01Icon";
import ListViewIcon from "@hugeicons/core-free-icons/ListViewIcon";
import MoreHorizontalIcon from "@hugeicons/core-free-icons/MoreHorizontalIcon";
import PauseIcon from "@hugeicons/core-free-icons/PauseIcon";
import SparklesIcon from "@hugeicons/core-free-icons/SparklesIcon";
import InformationCircleIcon from "@hugeicons/core-free-icons/InformationCircleIcon";
import DragDropVerticalIcon from "@hugeicons/core-free-icons/DragDropVerticalIcon";

const icons = {
  logout: Logout01Icon, panel: SidebarLeft01Icon, chat: Chatting01Icon, back: ArrowLeft01Icon,
  search: Search01Icon, send: SentIcon, user: UserIcon, close: Cancel01Icon,
  menu: Menu01Icon, plug: PlugSocketIcon, check: Tick02Icon, book: Book02Icon,
  testing: TestTube01Icon, edit: Edit02Icon, broadcast: Megaphone01Icon,
  bolt: FlashIcon, settings: Settings01Icon, statistics: Analytics01Icon,
  customers: UserGroupIcon, integrations: Share08Icon, extensions: PuzzleIcon,
  tools: Wrench01Icon, voice: Call02Icon, help: HelpCircleIcon,
  chevron: ArrowDown01Icon, calendar: Calendar03Icon, filter: FilterHorizontalIcon,
  add: AddCircleIcon, branch: GitBranchIcon, appearance: PaintBoardIcon,
  userAdd: UserAdd01Icon, kanban: DashboardSquare01Icon, list: ListViewIcon,
  more: MoreHorizontalIcon, pause: PauseIcon, sparkles: SparklesIcon,
  info: InformationCircleIcon, drag: DragDropVerticalIcon,
};

export type DashboardIconName = keyof typeof icons;

export function DashboardIcon({ name, size = 20 }: { name: DashboardIconName; size?: number }) {
  return <PlumoIcon icon={icons[name]} size={size} />;
}
