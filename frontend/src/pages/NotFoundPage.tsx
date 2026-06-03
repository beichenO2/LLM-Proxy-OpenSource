import { Link } from "react-router-dom";
import { btnPrimaryClass } from "../lib/styles";
import { useDocumentTitle } from "../lib/use-document-title";

export default function NotFoundPage() {
  useDocumentTitle("页面未找到");

  return (
    <div className="flex flex-1 flex-col items-center justify-center p-8">
      <div className="text-center">
        <p className="text-6xl font-bold text-neutral-300">404</p>
        <h1 className="mt-4 text-xl font-semibold text-neutral-900">页面未找到</h1>
        <p className="mt-2 text-sm text-neutral-600">
          您访问的页面不存在或已被移动。
        </p>
        <Link to="/" className={`mt-6 inline-block ${btnPrimaryClass}`}>
          返回仪表盘
        </Link>
      </div>
    </div>
  );
}
