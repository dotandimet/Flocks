window.tweak_content=function() {
    var anchor=location.hash;
    if (anchor) {
        $(anchor).addClass('hilite').focus();
    }
    $('a:not(.internal-link)').attr('target','_blank');
}
$(function() {
    $.manageAjax.create('flocks',{queue:true}); 
    window.tweak_content();
});

window.populate_from_feed=function(ul,data) {
    for (e in data['entries']) { 
        if (e>=window.MAX_FEED_ENTRIES) { break; }
        entry=data['entries'][e];
        feed_dir=entry['feed_rtl']?'rtl':'ltr';
        var item_header=$('<div/>').addClass('toggler-label').addClass(feed_dir);
        item_header.append($('<div/>').addClass('item-time').text(entry['friendly_time']));
        item_header.append($('<span/>').addClass('feed-reference').text(entry['feed_title']));
        item_header.append(window.BUTTON_HTML[entry['feed_url']]);
        item_header.append(': ').append($('<a/>').addClass('entry_title').attr(
            'href',entry['link']).html(entry['title']));
        var li=$('<li/>').attr('id',entry['id']).append(
            item_header).append($('<input/>').addClass('toggler').attr('type','checkbox'));
        li.append($('<div/>').addClass('entry-description').addClass(feed_dir).html(entry['description']));
        li.data('modified',entry['modified']);
        var sameold=ul.find('#'+li.attr('id'));
        if (sameold.length) {
            sameold.eq(0).replaceWith(li);
        } else {
            var older=ul.find('li').filter(function() {
                return $(this).data('modified')<li.data('modified');
            });
            if (older.length) {
               	older.eq(0).before(li); 
            } else {
                ul.append(li);
            }
        }
    }
}

window.fetch_from_feed=function(ul_id,feed_title,feed_url) {
    var ul=$('#'+ul_id);
    var loading=$('<li/>').addClass('fetching-ajax').html(AJAX_LOADER_HTML).prepend('Loading '+feed_title+': ').data('modified','');
    ul.append(loading);
    $.manageAjax.add('flocks',{
        url:window.AJAX_FEED_URL,
        data:{url:feed_url},
        ul:ul,
        refresh:"window.fetch_from_feed('"+ul_id+"','"+feed_title+"','"+feed_url+"')",
        refresh_seconds:1000*window.FEED_REFRESH_SECONDS,
        loading:loading,
        success:function(data,textStatus,xhr,options){
            options['loading'].slideUp(500).remove();
            populate_from_feed(options['ul'],data);
            window.tweak_content();
            setTimeout(options['refresh'],options['refresh_seconds']);
        },
        error:function(data,textStatus,xhr,options){
            options['loading'].find('img').replaceWith('failed').prependTo(options['ul']).addClass('hilite').delay(10000).slideUp(500).remove();
            setTimeout(options['refresh'],options['refresh_seconds']);
        },
        abort:function(data,textStatus,xhr,options){
            options['loading'].find('img').replaceWith('aborted').prependTo(options['ul']).addClass('hilite').delay(10000).slideUp(500).remove();
            setTimeout(options['refresh'],options['refresh_seconds']);
        }
    });
}
window.abort_all_fetches = function() {
    $.manageAjax.clear('flocks');
    $('.fetching-ajax').slideUp(500).remove();
}

