import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// react-markdown does not render raw HTML unless a rehype-raw plugin is added,
// so model output cannot inject markup or scripts into the page.
const components = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer nofollow">
      {children}
    </a>
  ),
}

export default function Markdown({ children }) {
  return (
    <div className="prose-chat">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components} skipHtml>
        {children || ''}
      </ReactMarkdown>
    </div>
  )
}
